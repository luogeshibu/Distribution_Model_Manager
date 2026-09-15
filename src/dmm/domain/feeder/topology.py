from __future__ import annotations
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional
from dmm.domain.gfile.parser import GParser, GObject

@dataclass
class TopologyEndpoint:
    label: str
    x: float
    y: float
    kind: str
    xml_id: str = ""

class FeederTopologyResolver:
    def __init__(self, parser: Optional[GParser]=None):
        self.parser = parser or GParser(label_regex=r"^\d+$")

    @staticmethod
    def _refs(obj: GObject):
        raw=str(obj.attrs.get("link") or obj.attrs.get("node_area") or "")
        out=[]
        for part in raw.split(";"):
            bits=[x.strip() for x in part.split(",")]
            if len(bits)>=3 and bits[2]:
                out.append(bits[2])
        return list(dict.fromkeys(out))

    @staticmethod
    def _breaker_name(obj):
        text=(" ".join([obj.attrs.get("key_name",""),obj.attrs.get("p_NameString","")])).upper()
        m=re.findall(r"\bB\d+[A-Z0-9_-]*\b",text)
        return m[-1] if m else ""

    @staticmethod
    def _sort_key(ep):
        return (int(round(ep.y/40.0)),ep.x,ep.y,ep.label)

    @staticmethod
    def _line_ends(obj):
        b=obj.box
        return [(b.cx,b.top),(b.cx,b.bottom)] if b.h>=b.w else [(b.left,b.cy),(b.right,b.cy)]

    def resolve(self,g_file):
        parsed=self.parser.parse(g_file)
        graph=defaultdict(set)
        for obj in parsed.objects:
            if not obj.xml_id: continue
            for ref in self._refs(obj):
                graph[obj.xml_id].add(ref); graph[ref].add(obj.xml_id)

        anchors={}
        frames=self.parser.find_rmu_frames(parsed)
        assigned=self.parser.assign_rmu_label_candidates_globally(parsed,frames,["top","bottom","left","right"])
        for frame in frames:
            cands=list(assigned.get((frame.frame.xml_index,frame.frame.xml_id),[]))
            cands.sort(key=lambda x:(float(x.score),x.obj.xml_index))
            name=cands[0].text.strip() if cands else ""
            if not name: continue
            for br in self.parser.find_target_objects_in_frame(parsed,frame,["CBreakerDis"]):
                port=str(br.attrs.get("p_NameString") or br.attrs.get("key_name") or "").strip().upper()
                if re.fullmatch(r"[YQ]\d+",port):
                    anchors[br.xml_id]=TopologyEndpoint(f"{name}-{port}",br.box.cx,br.box.cy,"RMU_PORT",br.xml_id)
        for obj in parsed.objects:
            if obj.tag=="CBreaker":
                name=self._breaker_name(obj)
                if name:
                    anchors[obj.xml_id]=TopologyEndpoint(name,obj.box.cx,obj.box.cy,"SOURCE_BREAKER",obj.xml_id)

        ext=[]
        for obj in parsed.objects:
            if obj.tag.lower() == "text":
                m=re.fullmatch(r"\((\d+)\)",str(obj.attrs.get("ts") or "").strip())
                if m: ext.append((m.group(1),obj.box.cx,obj.box.cy,obj.xml_id))

        def search(start,blocked):
            q=deque([(start,0)]); vis={blocked}; found=[]
            while q:
                node,d=q.popleft()
                if node in vis: continue
                vis.add(node)
                if node in anchors:
                    found.append((d,anchors[node])); continue
                if d>=18: continue
                for n in graph.get(node,()):
                    if n not in vis:q.append((n,d+1))
            if not found:return None
            found.sort(key=lambda x:(x[0],self._sort_key(x[1])))
            return found[0][1]

        result={}
        for fl in [o for o in parsed.objects if o.tag=="FeedLine"]:
            eps=[]
            for ref in self._refs(fl):
                ep=search(ref,fl.xml_id)
                if ep: eps.append(ep)
            uniq={(e.kind,e.xml_id,e.label):e for e in eps}; eps=list(uniq.values())
            if len(eps)==1:
                known=eps[0]
                far=max(self._line_ends(fl),key=lambda p:(p[0]-known.x)**2+(p[1]-known.y)**2)
                nearby=[]
                for name,x,y,xid in ext:
                    dist=((x-far[0])**2+(y-far[1])**2)**0.5
                    if dist<=190: nearby.append((dist,name,x,y,xid))
                if nearby:
                    nearby.sort()
                    _,name,x,y,xid=nearby[0]
                    eps.append(TopologyEndpoint(name,x,y,"RMU_UNKNOWN_PORT",xid))
            eps.sort(key=self._sort_key)
            if len(eps)==2: name=f"{eps[0].label}_{eps[1].label}"; status="RESOLVED"
            elif len(eps)==1: name=eps[0].label; status="PARTIAL"
            elif len(eps)>2: name=""; status="BRANCH_AMBIGUOUS"
            else: name=""; status="UNRESOLVED"
            result[str(fl.xml_id)]={"section_name":name,"topology_status":status,"endpoint_labels":[e.label for e in eps],"endpoint_kinds":[e.kind for e in eps]}
        return result

class FeederDrawingTopologyClassifier:
    """Classify a G drawing from electrical topology, not raw Bus count.

    Some G files contain tiny 6x6 ``Bus`` objects that are only connection
    nodes.  Counting those objects as independent busbars creates false
    MULTI_FEEDER_COMPOSITE results.  The classifier therefore separates
    effective busbars from point nodes, removes effective busbars from the
    explicit link graph, and counts independent source branches that leave
    those busbars.

    Feeder-title text is retained as an independent strong signal so overview
    drawings with sparse/unlinked electrical objects can still be identified.
    """

    _FEEDER_TITLE_RE = re.compile(
        r"\b([A-Z]{2,}[A-Z0-9]*)(?:[-_\s]+)(\d{1,3})\b",
        re.I,
    )

    def __init__(self, parser: Optional[GParser] = None):
        self.parser = parser or GParser()

    @staticmethod
    def _is_effective_busbar(obj: GObject) -> bool:
        if obj.tag != "Bus":
            return False
        major = max(float(obj.box.w), float(obj.box.h))
        minor = max(min(float(obj.box.w), float(obj.box.h)), 1.0)
        named = bool(
            str(obj.attrs.get("key_name") or "").strip()
            or str(obj.attrs.get("keyid") or "").strip()
        )
        # 6x6 (and similar) Bus objects are junction/connection points, not
        # physical busbars.  Real busbars are elongated and materially larger.
        return (major >= 40.0 and major / minor >= 3.0) or (named and major >= 20.0)

    @staticmethod
    def _point_to_box_distance(x: float, y: float, obj: GObject) -> float:
        box = obj.box
        dx = max(float(box.left) - x, 0.0, x - float(box.right))
        dy = max(float(box.top) - y, 0.0, y - float(box.bottom))
        return (dx * dx + dy * dy) ** 0.5

    @classmethod
    def _feeder_title_tokens(cls, parsed, busbars):
        tokens = set()
        occurrences = []
        for obj in parsed.objects:
            if obj.tag.lower() != "text":
                continue
            text = str(obj.attrs.get("ts") or "").strip().upper().replace("\n", " ")
            match = cls._FEEDER_TITLE_RE.search(text)
            if not match:
                continue
            token = f"{match.group(1).upper()}-{match.group(2)}"
            if busbars:
                distance = min(
                    cls._point_to_box_distance(obj.box.cx, obj.box.cy, bus)
                    for bus in busbars
                )
                if distance > 500.0:
                    continue
            else:
                distance = None
            tokens.add(token)
            occurrences.append({
                "token": token,
                "xml_id": str(obj.xml_id or ""),
                "x": float(obj.box.cx),
                "y": float(obj.box.cy),
                "bus_distance": None if distance is None else round(float(distance), 3),
            })
        return sorted(tokens), occurrences

    def classify(self, source):
        parsed = source if hasattr(source, "objects") else self.parser.parse(source)
        by_id = {str(obj.xml_id): obj for obj in parsed.objects if obj.xml_id}
        graph = defaultdict(set)
        for obj in parsed.objects:
            if not obj.xml_id:
                continue
            for ref in FeederTopologyResolver._refs(obj):
                ref = str(ref)
                if ref not in by_id:
                    continue
                graph[str(obj.xml_id)].add(ref)
                graph[ref].add(str(obj.xml_id))

        raw_buses = [obj for obj in parsed.objects if obj.tag == "Bus"]
        busbars = [obj for obj in raw_buses if self._is_effective_busbar(obj)]
        busbar_ids = {str(obj.xml_id) for obj in busbars if obj.xml_id}

        title_tokens, title_occurrences = self._feeder_title_tokens(parsed, busbars)

        seen = set()
        source_branches = []
        tie_branch_count = 0
        for xml_id in by_id:
            if xml_id in busbar_ids or xml_id in seen:
                continue
            stack = [xml_id]
            seen.add(xml_id)
            members = []
            while stack:
                current = stack.pop()
                members.append(current)
                for nxt in graph.get(current, ()):
                    if nxt in busbar_ids or nxt in seen:
                        continue
                    seen.add(nxt)
                    stack.append(nxt)

            touched_busbars = set()
            for member in members:
                touched_busbars.update(graph.get(member, set()) & busbar_ids)
            if not touched_busbars:
                continue

            counts = defaultdict(int)
            for member in members:
                counts[by_id[member].tag] += 1

            if len(touched_busbars) >= 2 and counts["CBreaker"]:
                tie_branch_count += 1

            if len(touched_busbars) == 1 and counts["CBreaker"]:
                source_branches.append({
                    "busbar_ids": sorted(touched_busbars),
                    "breaker_count": counts["CBreaker"],
                    "feedline_count": counts["FeedLine"],
                    "connectline_count": counts["ConnectLine"],
                    "member_count": len(members),
                })

        feeder_source_branches = [
            item for item in source_branches if item["feedline_count"] > 0
        ]
        source_cbreakers = [obj for obj in parsed.objects if obj.tag == "CBreaker"]
        source_cbreaker_count = len(source_cbreakers)
        feedline_count = sum(1 for obj in parsed.objects if obj.tag == "FeedLine")
        connectline_count = sum(1 for obj in parsed.objects if obj.tag == "ConnectLine")

        # v4.1.9 classification contract:
        #   * CBreaker is the station feeder-source breaker object.
        #   * CBreakerDis is an RMU/internal switch and MUST NOT be counted here.
        # In current SEC G drawings this is the strongest and simplest signal:
        # exactly one source CBreaker means a single-feeder drawing, while two or
        # more source CBreakers mean a composite drawing.  The richer electrical
        # topology remains a fallback only for legacy/incomplete files where no
        # CBreaker exists.
        if source_cbreaker_count == 1:
            drawing_type = "SINGLE_FEEDER"
            reason = "SINGLE_SOURCE_CBREAKER"
            confidence = "HIGH"
        elif source_cbreaker_count >= 2:
            drawing_type = "MULTI_FEEDER_COMPOSITE"
            reason = "MULTIPLE_SOURCE_CBREAKERS"
            confidence = "HIGH"
        elif len(feeder_source_branches) >= 2:
            drawing_type = "MULTI_FEEDER_COMPOSITE"
            reason = "TOPOLOGY_FALLBACK_MULTIPLE_INDEPENDENT_SOURCE_BRANCHES"
            confidence = "MEDIUM"
        elif len(feeder_source_branches) == 1:
            if len(source_branches) >= 2 and len(title_tokens) >= 2:
                drawing_type = "MULTI_FEEDER_COMPOSITE"
                reason = "TOPOLOGY_FALLBACK_MULTIPLE_BUS_SOURCE_BRANCHES_WITH_TITLES"
            else:
                drawing_type = "SINGLE_FEEDER"
                reason = "TOPOLOGY_FALLBACK_SINGLE_SOURCE_BRANCH"
            confidence = "MEDIUM"
        elif len(source_branches) >= 2 and len(title_tokens) >= 2:
            drawing_type = "MULTI_FEEDER_COMPOSITE"
            reason = "TOPOLOGY_FALLBACK_MULTIPLE_BUS_SOURCE_BRANCHES_WITH_TITLES"
            confidence = "MEDIUM"
        elif len(title_tokens) >= 2:
            drawing_type = "MULTI_FEEDER_COMPOSITE"
            reason = "TOPOLOGY_FALLBACK_MULTIPLE_FEEDER_TITLE_ANCHORS"
            confidence = "MEDIUM"
        elif len(title_tokens) == 1:
            drawing_type = "SINGLE_FEEDER"
            reason = "TOPOLOGY_FALLBACK_SINGLE_FEEDER_TITLE"
            confidence = "MEDIUM"
        elif len(busbars) == 1:
            drawing_type = "SINGLE_FEEDER"
            reason = "TOPOLOGY_FALLBACK_SINGLE_EFFECTIVE_BUSBAR"
            confidence = "LOW"
        else:
            drawing_type = "AMBIGUOUS"
            reason = "INSUFFICIENT_TOPOLOGY_EVIDENCE"
            confidence = "LOW"

        return {
            "parsed": parsed,
            "drawing_type": drawing_type,
            "classification_reason": reason,
            "classification_confidence": confidence,
            "source_cbreaker_count": source_cbreaker_count,
            "source_cbreaker_ids": [str(obj.xml_id or "") for obj in source_cbreakers],
            "bus_count": len(raw_buses),
            "effective_busbar_count": len(busbars),
            "effective_busbar_ids": [str(obj.xml_id or "") for obj in busbars],
            "feedline_count": feedline_count,
            "connectline_count": connectline_count,
            "feeder_title_count": len(title_tokens),
            "feeder_title_tokens": title_tokens,
            "feeder_title_occurrences": title_occurrences,
            "bus_source_branch_count": len(source_branches),
            "feeder_source_branch_count": len(feeder_source_branches),
            "bus_tie_branch_count": tie_branch_count,
        }
