# -*- coding: utf-8 -*-
"""إنشاء مصفوفة الكفاءات واللوجيغرام مع كشف العلاقات غير المحسومة."""
from __future__ import annotations
from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple
import pandas as pd


class LogigrammeGenerator:
    MODES = {
        "APC_strict": {"label": "APC الصارم", "description": "يعرض علاقات القبلية المصرح بها فقط؛ لا يفرض تسلسلاً غير موثق بين الكفاءات."},
        "traditionnel": {"label": "التوازي التقليدي", "description": "تنظيم متوازٍ للمقاييس، مع الاحتفاظ بعلاقات القبلية المصرح بها."},
    }

    @staticmethod
    def _competence_name(item: Dict[str, Any]) -> str:
        return str(item.get("label_ar") or item.get("label") or item.get("label_fr") or "كفاءة غير معنونة").strip()

    @staticmethod
    def _competence_id(item: Dict[str, Any]) -> str:
        value = item.get("id") or item.get("code") or item.get("label_ar") or item.get("label")
        if value is None or not str(value).strip():
            raise ValueError("توجد كفاءة دون id أو code أو اسم صالح.")
        return str(value).strip()

    @staticmethod
    def _extract_prerequisites(item: Dict[str, Any]) -> List[str]:
        values = item.get("prerequisites", item.get("prerequis", []))
        if values is None: return []
        if isinstance(values, str): values = [x.strip() for x in values.replace(";", "\n").splitlines() if x.strip()]
        if not isinstance(values, (list, tuple, set)): return []
        result = []
        for value in values:
            if isinstance(value, dict): value = value.get("id") or value.get("code") or value.get("label") or value.get("nom")
            if value is not None and str(value).strip() and str(value).strip() not in result: result.append(str(value).strip())
        return result

    def _prepare(self, competences: List[Dict[str, Any]]):
        if not isinstance(competences, list): raise TypeError("قائمة الكفاءات يجب أن تكون list.")
        by_id, aliases, duplicate_ids = {}, {}, []
        for item in competences:
            if not isinstance(item, dict): raise TypeError("كل عنصر في الكفاءات يجب أن يكون قاموساً.")
            cid = self._competence_id(item)
            if cid in by_id:
                duplicate_ids.append(cid)
                continue
            by_id[cid] = item
            for alias in (cid, item.get("code"), item.get("id"), item.get("label"), item.get("label_ar"), item.get("label_fr")):
                if alias is not None and str(alias).strip(): aliases[str(alias).strip()] = cid
        if duplicate_ids: raise ValueError("معرفات كفاءات مكررة: " + "، ".join(sorted(set(duplicate_ids))))
        graph, indegree, unknown = defaultdict(set), {k: 0 for k in by_id}, []
        normalized_prereq = {}
        for cid, item in by_id.items():
            normalized_prereq[cid] = []
            for raw in self._extract_prerequisites(item):
                resolved = aliases.get(raw)
                if not resolved:
                    unknown.append({"competence": cid, "prerequisite": raw})
                    continue
                if resolved == cid: 
                    unknown.append({"competence": cid, "prerequisite": raw, "issue": "اعتماد ذاتي"})
                    continue
                if cid not in graph[resolved]:
                    graph[resolved].add(cid); indegree[cid] += 1
                normalized_prereq[cid].append(resolved)
        return by_id, aliases, graph, indegree, normalized_prereq, unknown

    @staticmethod
    def _find_cycles(graph, nodes):
        # Tarjan: تحديد العقد الموجودة فعلاً داخل الدورات، لا كل العقد التابعة لها.
        index, stack, on_stack, indices, low, cycles = 0, [], set(), {}, {}, []
        def visit(v):
            nonlocal index
            indices[v] = low[v] = index; index += 1
            stack.append(v); on_stack.add(v)
            for w in graph[v]:
                if w not in indices: visit(w); low[v] = min(low[v], low[w])
                elif w in on_stack: low[v] = min(low[v], indices[w])
            if low[v] == indices[v]:
                component = []
                while True:
                    w = stack.pop(); on_stack.remove(w); component.append(w)
                    if w == v: break
                if len(component) > 1 or (len(component) == 1 and component[0] in graph[component[0]]): cycles.append(sorted(component))
        for node in nodes:
            if node not in indices: visit(node)
        return cycles

    def _topological_order(self, competences: List[Dict[str, Any]]):
        by_id, aliases, graph, indegree, prereq, unknown = self._prepare(competences)
        degree = dict(indegree)
        queue = deque(sorted(k for k, v in degree.items() if v == 0)); order = []
        while queue:
            node = queue.popleft(); order.append(node)
            for child in sorted(graph[node]):
                degree[child] -= 1
                if degree[child] == 0: queue.append(child)
        cycles = self._find_cycles(graph, list(by_id))
        blocked = sorted(set(by_id) - set(order) - {x for c in cycles for x in c})
        return order, cycles, blocked, unknown, by_id, prereq

    @staticmethod
    def _dependency_levels(order, prereq):
        """حساب مستويات القبلية؛ العناصر المستقلة لا تُمنح ترتيباً بيداغوجياً مصطنعاً."""
        levels = {}
        for cid in order:
            parents = prereq.get(cid, [])
            levels[cid] = 1 + max((levels.get(parent, 0) for parent in parents), default=0) if parents else 1
        return levels

    def generer_matrice(self, competences: List[Dict[str, Any]], mode: str = "APC_strict") -> pd.DataFrame:
        if mode not in self.MODES:
            raise ValueError(f"وضع غير معروف: {mode}")
        order, cycles, blocked, unknown, by_id, prereq = self._topological_order(competences)
        levels = self._dependency_levels(order, prereq)
        has_dependencies = any(prereq.values())
        rows = []
        for cid in order:
            item = by_id[cid]
            rows.append({
                "مستوى القبلية": f"L{levels[cid]}" if has_dependencies else "غير محدد في المرجع",
                "الرمز": item.get("code", cid),
                "العنصر التأهيلي": self._competence_name(item),
                "العناصر القبلية المعروفة": "، ".join(self._competence_name(by_id[p]) for p in prereq[cid]) or "غير محددة في البيانات",
                "طبيعة البرمجة": "وفق علاقات القبلية المصرح بها" if mode == "APC_strict" else "متوازية تنظيمياً مع احترام القبلية",
                "قاعدة الانطلاق": "بعد استيفاء العناصر القبلية والتحقق منها" if prereq[cid] else "لا توجد قبلية مصرح بها",
                "المصادقة": "تحدد شبكة المصادقة وأدلتها من المرجع/الأستاذ؛ لا تفترض آلياً",
                "المجموعة": f"G{levels[cid]}" if has_dependencies else "غير محددة",
            })
        return pd.DataFrame(rows)

    def generer_processus(self, competences: List[Dict[str, Any]], mode: str = "APC_strict") -> Dict[str, Any]:
        if mode not in self.MODES:
            raise ValueError(f"وضع غير معروف: {mode}")
        order, cycles, blocked, unknown, by_id, prereq = self._topological_order(competences)
        levels = self._dependency_levels(order, prereq)
        has_dependencies = any(prereq.values())
        nodes = []
        for cid in order:
            item = by_id[cid]
            nodes.append({
                "id": cid,
                "label": f"{item.get('code', cid)}\n{self._competence_name(item)}",
                "group": f"G{levels[cid]}" if has_dependencies else "غير محددة",
                "order": levels[cid] if has_dependencies else None,
                "ordering_status": "مستنتج من علاقات القبلية" if has_dependencies else "لا توجد علاقات قبلية موثقة؛ ترتيب العرض ليس ترتيباً بيداغوجياً",
            })
        edges = [{"from": p, "to": cid, "label": "عنصر قبلي مصرح به"}
                 for cid, ps in prereq.items() for p in ps]
        return {
            "mode": mode,
            "mode_description": self.MODES[mode]["description"],
            "nodes": nodes,
            "edges": edges,
            "cycles": cycles,
            "blocked_nodes": blocked,
            "unknown_prerequisites": unknown,
            "has_documented_dependencies": has_dependencies,
            "is_valid_dag": not cycles and not blocked and not unknown,
            "ordering_note": "المستويات تعكس علاقات القبلية الواردة فقط." if has_dependencies else "لم يحدد المرجع علاقات قبلية؛ تعرض العناصر دون ترتيب بيداغوجي مفترض.",
        }

    @staticmethod
    def _label(value: Any) -> str:
        if isinstance(value, dict): return str(value.get("label_ar") or value.get("label") or value.get("label_fr") or "—")
        return str(value or "—")

    def generer_dossier_ouverture(self, specialite: Dict[str, Any], competences: List[Dict[str, Any]], mode: str = "APC_strict") -> Dict[str, Any]:
        if mode not in self.MODES: raise ValueError(f"وضع غير معروف: {mode}")
        process = self.generer_processus(competences, mode)
        return {
            "intitule": "ملف تنظيم المسار البيداغوجي (Dossier d'ouverture)",
            "specialite": self._label(specialite.get("label_ar") or specialite.get("label") or specialite.get("label_fr")),
            "code_specialite": specialite.get("code", "—"),
            "secteur": self._label(specialite.get("secteur")),
            "domaine": self._label(specialite.get("domaine")),
            "sous_domaine": self._label(specialite.get("sous_domaine")),
            "mode": self.MODES[mode]["label"], "principe": self.MODES[mode]["description"],
            "nombre_competences_selectionnees": len(competences),
            "regle_RES": "لا تُفرض مصادقة أو علاقة انتقال غير واردة في بيانات المرجع؛ يجب توثيقها في شبكة مستقلة.",
            "controle_coherence": {"cycles": process["cycles"], "blocked_nodes": process["blocked_nodes"], "unknown_prerequisites": process["unknown_prerequisites"], "is_valid_dag": process["is_valid_dag"]},
        }
