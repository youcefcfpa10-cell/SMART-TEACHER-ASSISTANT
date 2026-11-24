
# -*- coding: utf-8 -*-
"""
SMART TEACHER ASSISTANT — APC
محرك مصفوفة الكفاءات واللوجيغرام ومراقبة الاتساق.

المبادئ:
- عدم اختلاق علاقات قبلية.
- عدم فرض ترتيب بيداغوجي غير موثق.
- الفصل بين عناصر modQ والكفاءات المهنية.
- التمييز بين البيانات المرجعية والمدخلة والمقترحة.
- كشف التكرار والدورات والعلاقات غير المحسومة.
- مراقبة اتساق بطاقات التعلم مع المصفوفة.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


class LogigrammeGenerator:

    MODES = {
        "APC_strict": {
            "label": "APC الصارم",
            "description": (
                "يعرض علاقات القبلية المصرح بها فقط، "
                "ولا يفرض تسلسلاً غير موثق."
            ),
        },
        "traditionnel": {
            "label": "التنظيم المتوازي التقليدي",
            "description": (
                "تنظيم متوازٍ للعناصر، مع الاحتفاظ "
                "بعلاقات القبلية المصرح بها."
            ),
        },
    }

    # --------------------------------------------------
    # 1. معالجة النصوص
    # --------------------------------------------------

    @staticmethod
    def _text(value: Any, default: str = "") -> str:

        if value is None:
            return default

        text = str(value).strip()

        if text.casefold() in {"", "nan", "none", "null"}:
            return default

        return text

    @classmethod
    def _competence_name(cls, item: Dict[str, Any]) -> str:

        return cls._text(
            item.get("label_ar")
            or item.get("label")
            or item.get("label_fr")
            or item.get("nom"),
            "عنصر غير معنّون",
        )

    @classmethod
    def _competence_id(cls, item: Dict[str, Any]) -> str:

        value = (
            item.get("id")
            or item.get("code")
            or item.get("label_ar")
            or item.get("label")
        )

        if value is None or not str(value).strip():

            raise ValueError(
                "يوجد عنصر دون id أو code أو اسم صالح."
            )

        return str(value).strip()

    @classmethod
    def _label(cls, value: Any) -> str:

        if isinstance(value, dict):

            return cls._text(
                value.get("label_ar")
                or value.get("label")
                or value.get("label_fr")
                or value.get("nom"),
                "—",
            )

        return cls._text(value, "—")

    # --------------------------------------------------
    # 2. تصنيف العناصر
    # --------------------------------------------------

    @classmethod
    def _is_modq(cls, item: Dict[str, Any]) -> bool:

        if item.get("is_modq") is True:
            return True

        markers = [
            item.get("item_type"),
            item.get("type"),
            item.get("category"),
            item.get("source_group"),
            item.get("group"),
            item.get("origin"),
            item.get("source"),
            item.get("classification"),
        ]

        for marker in markers:

            value = cls._text(marker).casefold()

            if "modq" in value:
                return True

        return False

    @classmethod
    def _item_classification(
        cls,
        item: Dict[str, Any]
    ) -> str:

        if cls._is_modq(item):
            return "عنصر modQ غير مثبت ككفاءة مهنية"

        return cls._text(
            item.get("classification"),
            "عنصر يحتاج إلى التحقق من تصنيفه"
        )

    @classmethod
    def _source_status(
        cls,
        item: Dict[str, Any],
        field_name: str = ""
    ) -> str:

        field_sources = item.get("field_sources", {})

        if isinstance(field_sources, dict) and field_name:

            source = cls._text(
                field_sources.get(field_name)
            ).casefold()

            if source in {
                "rnfc",
                "referentiel",
                "référentiel",
                "مرجعي",
                "مرجعية",
            }:
                return "مرجعي RNFC"

            if source in {
                "proposed",
                "proposal",
                "مقترح",
            }:
                return "مقترح"

            if source:
                return "بيانات مدخلة غير متحقق من مرجعيتها"

        source = cls._text(
            item.get("source")
            or item.get("provenance")
            or item.get("data_source")
        ).casefold()

        if source in {
            "rnfc",
            "referentiel",
            "référentiel",
            "مرجعي",
            "مرجعية",
        }:
            return "مرجعي RNFC"

        if source in {"proposed", "proposal", "مقترح"}:
            return "مقترح"

        return "بيانات مدخلة غير متحقق من مرجعيتها"

    # --------------------------------------------------
    # 3. استخراج العلاقات القبلية
    # --------------------------------------------------

    @classmethod
    def _extract_prerequisites(
        cls,
        item: Dict[str, Any]
    ) -> List[str]:

        values = item.get(
            "prerequisites",
            item.get("prerequis", [])
        )

        if values is None:
            return []

        if isinstance(values, str):

            values = [
                x.strip()
                for x in values.replace(";", "\n").splitlines()
                if x.strip()
            ]

        elif isinstance(values, dict):

            values = [values]

        if not isinstance(values, (list, tuple, set)):
            return []

        result = []

        for value in values:

            if isinstance(value, dict):

                value = (
                    value.get("id")
                    or value.get("code")
                    or value.get("label_ar")
                    or value.get("label")
                    or value.get("nom")
                )

            if value is None:
                continue

            text = str(value).strip()

            if text and text not in result:
                result.append(text)

        return result

    # --------------------------------------------------
    # 4. تحليل البيانات واكتشاف التكرار
    # --------------------------------------------------

    def analyser_donnees(
        self,
        competences: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        if not isinstance(competences, list):

            raise TypeError(
                "قائمة العناصر يجب أن تكون من النوع list."
            )

        ids = defaultdict(list)
        names = defaultdict(list)
        codes = defaultdict(list)

        modq_items = []
        other_items = []
        invalid_items = []

        for index, item in enumerate(competences):

            if not isinstance(item, dict):

                invalid_items.append({
                    "index": index,
                    "issue": "العنصر ليس قاموساً",
                })

                continue

            cid = (
                item.get("id")
                or item.get("code")
                or item.get("label_ar")
                or item.get("label")
            )

            if cid is None or not str(cid).strip():

                invalid_items.append({
                    "index": index,
                    "issue": "معرف أو اسم مفقود",
                })

                continue

            cid = str(cid).strip()

            ids[cid].append(index)

            name = self._competence_name(item)

            if name != "عنصر غير معنّون":
                names[name.casefold()].append(cid)

            code = self._text(item.get("code"))

            if code:
                codes[code].append(cid)

            if self._is_modq(item):
                modq_items.append(cid)
            else:
                other_items.append(cid)

        duplicate_ids = [
            {
                "id": key,
                "indexes": indexes,
            }
            for key, indexes in ids.items()
            if len(indexes) > 1
        ]

        duplicate_names = [
            {
                "name": key,
                "ids": values,
            }
            for key, values in names.items()
            if len(set(values)) > 1
        ]

        duplicate_codes = [
            {
                "code": key,
                "ids": values,
            }
            for key, values in codes.items()
            if len(set(values)) > 1
        ]

        return {

            "total": len(competences),

            "valid_items": len(competences) - len(invalid_items),

            "modq_count": len(modq_items),

            "other_items_count": len(other_items),

            "modq_items": modq_items,

            "duplicate_ids": duplicate_ids,

            "duplicate_names": duplicate_names,

            "duplicate_codes": duplicate_codes,

            "invalid_items": invalid_items,

            "has_duplicates": bool(
                duplicate_ids
                or duplicate_names
                or duplicate_codes
            ),

            "is_valid": not bool(
                duplicate_ids or invalid_items
            ),

        }

    # --------------------------------------------------
    # 5. تجهيز الرسم البياني
    # --------------------------------------------------

    def _prepare(
        self,
        competences: List[Dict[str, Any]]
    ):

        analysis = self.analyser_donnees(competences)

        if analysis["invalid_items"]:

            raise ValueError(
                "توجد عناصر غير صالحة: "
                + str(analysis["invalid_items"])
            )

        if analysis["duplicate_ids"]:

            duplicated = [
                item["id"]
                for item in analysis["duplicate_ids"]
            ]

            raise ValueError(
                "معرفات مكررة: "
                + "، ".join(duplicated)
            )

        by_id = {}
        aliases = {}
        ambiguous_aliases = set()

        for item in competences:

            cid = self._competence_id(item)

            by_id[cid] = item

            item_aliases = [
                cid,
                item.get("code"),
                item.get("id"),
                item.get("label"),
                item.get("label_ar"),
                item.get("label_fr"),
                item.get("nom"),
            ]

            for alias in item_aliases:

                if alias is None:
                    continue

                key = str(alias).strip()

                if not key:
                    continue

                previous = aliases.get(key)

                if previous is None:
                    aliases[key] = cid

                elif previous != cid:
                    ambiguous_aliases.add(key)

        # حذف الأسماء الملتبسة حتى لا تربط بعنصر خاطئ.
        for alias in ambiguous_aliases:
            aliases.pop(alias, None)

        graph = defaultdict(set)

        indegree = {
            key: 0
            for key in by_id
        }

        normalized_prereq = {
            key: []
            for key in by_id
        }

        unknown = []

        for cid, item in by_id.items():

            for raw in self._extract_prerequisites(item):

                resolved = aliases.get(raw)

                if not resolved:

                    unknown.append({

                        "competence": cid,

                        "prerequisite": raw,

                        "issue": (
                            "معرف غير موجود أو اسم ملتبس"
                        ),

                    })

                    continue

                if resolved == cid:

                    unknown.append({

                        "competence": cid,

                        "prerequisite": raw,

                        "issue": "اعتماد ذاتي",

                    })

                    continue

                if cid not in graph[resolved]:

                    graph[resolved].add(cid)

                    indegree[cid] += 1

                if resolved not in normalized_prereq[cid]:
                    normalized_prereq[cid].append(resolved)

        for alias in sorted(ambiguous_aliases):

            unknown.append({

                "competence": "غير محدد",

                "prerequisite": alias,

                "issue": "اسم مستعمل لأكثر من عنصر",

            })

        return (
            by_id,
            aliases,
            graph,
            indegree,
            normalized_prereq,
            unknown,
        )

    # --------------------------------------------------
    # 6. كشف الدورات
    # --------------------------------------------------

    @staticmethod
    def _find_cycles(graph, nodes):

        index = 0

        stack = []
        on_stack = set()

        indices = {}
        low = {}

        cycles = []

        def visit(v):

            nonlocal index

            indices[v] = index
            low[v] = index

            index += 1

            stack.append(v)
            on_stack.add(v)

            for w in graph[v]:

                if w not in indices:

                    visit(w)

                    low[v] = min(
                        low[v],
                        low[w]
                    )

                elif w in on_stack:

                    low[v] = min(
                        low[v],
                        indices[w]
                    )

            if low[v] == indices[v]:

                component = []

                while True:

                    w = stack.pop()

                    on_stack.remove(w)

                    component.append(w)

                    if w == v:
                        break

                if len(component) > 1:

                    cycles.append(
                        sorted(component)
                    )

                elif component[0] in graph[component[0]]:

                    cycles.append(component)

        for node in nodes:

            if node not in indices:
                visit(node)

        return cycles

    # --------------------------------------------------
    # 7. الترتيب الطوبولوجي
    # --------------------------------------------------

    def _topological_order(
        self,
        competences: List[Dict[str, Any]]
    ):

        (
            by_id,
            aliases,
            graph,
            indegree,
            prereq,
            unknown,
        ) = self._prepare(competences)

        degree = dict(indegree)

        queue = deque(
            sorted(
                key
                for key, value in degree.items()
                if value == 0
            )
        )

        order = []

        while queue:

            node = queue.popleft()

            order.append(node)

            for child in sorted(graph[node]):

                degree[child] -= 1

                if degree[child] == 0:
                    queue.append(child)

        cycles = self._find_cycles(
            graph,
            list(by_id)
        )

        cycle_nodes = {
            node
            for cycle in cycles
            for node in cycle
        }

        blocked = sorted(
            set(by_id)
            - set(order)
            - cycle_nodes
        )

        return (
            order,
            cycles,
            blocked,
            unknown,
            by_id,
            prereq,
        )

    # --------------------------------------------------
    # 8. حساب مستويات القبلية
    # --------------------------------------------------

    @staticmethod
    def _dependency_levels(order, prereq):

        levels = {}

        for cid in order:

            parents = prereq.get(cid, [])

            if parents:

                levels[cid] = 1 + max(
                    levels.get(parent, 0)
                    for parent in parents
                )

            else:

                levels[cid] = 1

        return levels

    # --------------------------------------------------
    # 9. إنشاء المصفوفة
    # --------------------------------------------------

    def generer_matrice(
        self,
        competences: List[Dict[str, Any]],
        mode: str = "APC_strict"
    ) -> pd.DataFrame:

        if mode not in self.MODES:

            raise ValueError(
                f"وضع غير معروف: {mode}"
            )

        (
            order,
            cycles,
            blocked,
            unknown,
            by_id,
            prereq,
        ) = self._topological_order(competences)

        levels = self._dependency_levels(
            order,
            prereq
        )

        has_dependencies = any(
            prereq.values()
        )

        rows = []

        for cid in order:

            item = by_id[cid]

            parents = prereq[cid]

            rows.append({

                "مستوى القبلية": (
                    f"L{levels[cid]}"
                    if has_dependencies
                    else "غير محدد في المرجع"
                ),

                "الرمز": item.get("code", cid),

                "العنصر التأهيلي": (
                    self._competence_name(item)
                ),

                "تصنيف العنصر": (
                    self._item_classification(item)
                ),

                "المصدر": self._source_status(item),

                "العناصر القبلية المعروفة": (
                    "، ".join(
                        self._competence_name(by_id[p])
                        for p in parents
                    )
                    if parents
                    else "غير محددة في البيانات"
                ),

                "مصدر العلاقة": (
                    "علاقة قبلية مصرح بها في البيانات"
                    if parents
                    else "لا توجد علاقة قبلية مصرح بها"
                ),

                "طبيعة البرمجة": (
                    "وفق علاقات القبلية المصرح بها"
                    if mode == "APC_strict"
                    else "تنظيم متوازٍ مع احترام القبلية"
                ),

                "قاعدة الانطلاق": (
                    "بعد استيفاء العناصر القبلية والتحقق منها"
                    if parents
                    else "لا توجد قبلية مصرح بها"
                ),

                "المصادقة": (
                    "تحدد أدلتها من المرجع أو الأستاذ؛ "
                    "لا تفترض آلياً"
                ),

                "المجموعة": (
                    f"G{levels[cid]}"
                    if has_dependencies
                    else "غير محددة"
                ),

            })

        columns = [

            "مستوى القبلية",
            "الرمز",
            "العنصر التأهيلي",
            "تصنيف العنصر",
            "المصدر",
            "العناصر القبلية المعروفة",
            "مصدر العلاقة",
            "طبيعة البرمجة",
            "قاعدة الانطلاق",
            "المصادقة",
            "المجموعة",

        ]

        return pd.DataFrame(
            rows,
            columns=columns
        )

    # --------------------------------------------------
    # 10. إنشاء بيانات اللوجيغرام
    # --------------------------------------------------

    def generer_processus(
        self,
        competences: List[Dict[str, Any]],
        mode: str = "APC_strict"
    ) -> Dict[str, Any]:

        if mode not in self.MODES:

            raise ValueError(
                f"وضع غير معروف: {mode}"
            )

        (
            order,
            cycles,
            blocked,
            unknown,
            by_id,
            prereq,
        ) = self._topological_order(competences)

        levels = self._dependency_levels(
            order,
            prereq
        )

        has_dependencies = any(
            prereq.values()
        )

        nodes = []

        for cid in order:

            item = by_id[cid]

            is_modq = self._is_modq(item)

            nodes.append({

                "id": cid,

                "code": self._text(
                    item.get("code"),
                    cid
                ),

                "label": (
                    f"{self._text(item.get('code'), cid)}\n"
                    f"{self._competence_name(item)}"
                ),

                "name": self._competence_name(item),

                "group": (
                    f"G{levels[cid]}"
                    if has_dependencies
                    else "غير محددة"
                ),

                "order": (
                    levels[cid]
                    if has_dependencies
                    else None
                ),

                "item_type": (
                    self._item_classification(item)
                ),

                "is_modq": is_modq,

                "source": self._source_status(item),

                "ordering_status": (
                    "مستنتج من علاقات القبلية المصرح بها"
                    if has_dependencies
                    else "ترتيب العرض ليس ترتيباً بيداغوجياً"
                ),

                "validation_required": True,

            })

        edges = []

        for cid, parents in prereq.items():

            for parent in parents:

                edges.append({

                    "from": parent,

                    "to": cid,

                    "label": "عنصر قبلي مصرح به",

                    "source": "بيانات مدخلة؛ تحقق من المرجعية",

                    "status": "غير متحقق من المصدر",

                })

        return {

            "mode": mode,

            "mode_label": self.MODES[mode]["label"],

            "mode_description": (
                self.MODES[mode]["description"]
            ),

            "nodes": nodes,

            "edges": edges,

            "cycles": cycles,

            "blocked_nodes": blocked,

            "unknown_prerequisites": unknown,

            "has_documented_dependencies": (
                has_dependencies
            ),

            "is_valid_dag": (
                not cycles
                and not blocked
                and not unknown
            ),

            "ordering_note": (

                "المستويات تعكس العلاقات القبلية "
                "الواردة في البيانات فقط."

                if has_dependencies

                else

                "لم تحدد البيانات علاقات قبلية؛ "
                "تعرض العناصر دون ترتيب بيداغوجي مفترض."

            ),

            "quality_status": (
                "يحتاج إلى مراجعة"
                if cycles or blocked or unknown
                else "لا توجد أخطاء بنيوية مكتشفة"
            ),

        }

    # --------------------------------------------------
    # 11. مراقبة اتساق بطاقات التعلم
    # --------------------------------------------------

    def controler_coherence(
        self,
        competences: List[Dict[str, Any]],
        fiches: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:

        analysis = self.analyser_donnees(
            competences
        )

        reference_ids = set()

        for item in competences:

            if not isinstance(item, dict):
                continue

            try:
                reference_ids.add(
                    self._competence_id(item)
                )
            except ValueError:
                continue

        report = {

            "reference_count": len(competences),

            "cards_count": 0,

            "missing_cards": [],

            "orphan_cards": [],

            "duplicate_cards": [],

            "classification_conflicts": [],

            "modq_cards": [],

            "issues": [],

        }

        if fiches is None:
            fiches = []

        if not isinstance(fiches, list):

            raise TypeError(
                "قائمة بطاقات التعلم يجب أن تكون list."
            )

        report["cards_count"] = len(fiches)

        cards_by_id = defaultdict(list)

        for index, fiche in enumerate(fiches):

            if not isinstance(fiche, dict):

                report["issues"].append({

                    "index": index,

                    "issue": "بطاقة التعلم ليست قاموساً",

                })

                continue

            competence = fiche.get(
                "competence",
                fiche
            )

            if not isinstance(competence, dict):
                competence = fiche

            cid = (

                competence.get("id")
                or competence.get("code")
                or fiche.get("id")
                or fiche.get("code")

            )

            if cid is None:

                report["issues"].append({

                    "index": index,

                    "issue": "بطاقة دون معرف",

                })

                continue

            cid = str(cid).strip()

            cards_by_id[cid].append(fiche)

        report["duplicate_cards"] = [

            cid

            for cid, cards in cards_by_id.items()

            if len(cards) > 1

        ]

        report["missing_cards"] = sorted(
            reference_ids - set(cards_by_id)
        )

        report["orphan_cards"] = sorted(
            set(cards_by_id) - reference_ids
        )

        source_items = {}

        for item in competences:

            if not isinstance(item, dict):
                continue

            try:
                source_items[
                    self._competence_id(item)
                ] = item
            except ValueError:
                continue

        for cid in sorted(
            reference_ids & set(cards_by_id)
        ):

            reference_item = source_items[cid]

            for fiche in cards_by_id[cid]:

                fiche_meta = fiche.get(
                    "metadata",
                    {}
                )

                if not isinstance(fiche_meta, dict):
                    fiche_meta = {}

                fiche_comp = fiche.get(
                    "competence",
                    {}
                )

                if not isinstance(fiche_comp, dict):
                    fiche_comp = {}

                card_is_modq = (

                    fiche_meta.get("is_modq") is True

                    or fiche_comp.get("is_modq") is True

                )

                ref_is_modq = self._is_modq(
                    reference_item
                )

                if card_is_modq != ref_is_modq:

                    report["classification_conflicts"].append({

                        "id": cid,

                        "reference_is_modq": ref_is_modq,

                        "card_is_modq": card_is_modq,

                    })

                if ref_is_modq:
                    report["modq_cards"].append(cid)

        report["is_consistent"] = not bool(

            report["missing_cards"]

            or report["orphan_cards"]

            or report["duplicate_cards"]

            or report["classification_conflicts"]

            or report["issues"]

        )

        report["teacher_validation_required"] = True

        return report

    # --------------------------------------------------
    # 12. ملف افتتاح التخصص
    # --------------------------------------------------

    def generer_dossier_ouverture(
        self,
        specialite: Dict[str, Any],
        competences: List[Dict[str, Any]],
        mode: str = "APC_strict"
    ) -> Dict[str, Any]:

        if mode not in self.MODES:

            raise ValueError(
                f"وضع غير معروف: {mode}"
            )

        if not isinstance(specialite, dict):

            raise TypeError(
                "بيانات التخصص يجب أن تكون قاموساً."
            )

        analysis = self.analyser_donnees(
            competences
        )

        process = self.generer_processus(
            competences,
            mode
        )

        matrix = self.generer_matrice(
            competences,
            mode
        )

        return {

            "intitule": (
                "ملف تنظيم المسار البيداغوجي "
                "(Dossier d'ouverture)"
            ),

            "specialite": self._label(

                specialite.get("label_ar")
                or specialite.get("label")
                or specialite.get("label_fr")

            ),

            "code_specialite": self._text(
                specialite.get("code"),
                "—"
            ),

            "secteur": self._label(
                specialite.get("secteur")
            ),

            "domaine": self._label(
                specialite.get("domaine")
            ),

            "sous_domaine": self._label(
                specialite.get("sous_domaine")
            ),

            "mode": self.MODES[mode]["label"],

            "principe": self.MODES[mode]["description"],

            "nombre_competences_selectionnees": (
                len(competences)
            ),

            "nombre_elements_modq": (
                analysis["modq_count"]
            ),

            "regle_RES": (

                "لا تفرض مصادقة أو علاقة انتقال "
                "غير واردة في بيانات المرجع. "
                "يجب توثيق العلاقات المقترحة "
                "في مجموعة مستقلة."
            ),

            "matrice": matrix.to_dict(
                orient="records"
            ),

            "logigramme": process,

            "diagnostic_donnees": analysis,

            "controle_coherence": {

                "cycles": process["cycles"],

                "blocked_nodes": process["blocked_nodes"],

                "unknown_prerequisites": (
                    process["unknown_prerequisites"]
                ),

                "is_valid_dag": process["is_valid_dag"],

                "has_duplicates": analysis["has_duplicates"],

            },

            "teacher_validation_required": True,

        }
