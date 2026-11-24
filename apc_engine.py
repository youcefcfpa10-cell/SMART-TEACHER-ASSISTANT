
# -*- coding: utf-8 -*-
"""
SMART TEACHER ASSISTANT — APC
محرك بناء بطاقات التعلم وفق المقاربة بالكفاءات.

المبادئ:
- الفصل بين البيانات المرجعية والمدخلة والمقترحة.
- عدم اعتبار عناصر modQ كفاءات مهنية مثبتة.
- عدم اختلاق علاقات قبلية أو معايير أداء مرجعية.
- المحافظة على توافق المخرجات مع app.py.
- تجهيز البيانات لمحرك logigramme.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class APCEngine:

    PHASES = [
        ("الوضعية المشكلة", "Situation-problème", 10),
        ("تعبئة الموارد", "Mobilisation des ressources", 10),
        ("التعلم والتطبيق الموجه", "Apprentissage et application guidée", 45),
        ("الإدماج والتقييم", "Intégration et évaluation", 25),
        ("المعالجة ونقل التعلم", "Remédiation et transfert", 10),
    ]

    DEFAULT_CRITERIA = [
        "مطابقة الإنجاز للنتيجة المطلوبة",
        "احترام إجراءات العمل",
        "الجودة والدقة",
        "الاستقلالية والتنظيم",
    ]

    DEFAULT_WEIGHTS = [40, 30, 20, 10]

    FIELD_ALIASES = {
        "resources": ("resources", "ressources", "savoirs"),
        "prerequisites": ("prerequisites", "prerequis"),
        "criteria": ("criteria", "criteres"),
        "indicators": ("indicators", "indicateurs"),
        "conditions": ("conditions", "conditions_realisation"),
    }

    def __init__(self, duree_totale_minutes: int = 120) -> None:

        if isinstance(duree_totale_minutes, bool):
            raise ValueError("مدة الدرس يجب أن تكون عدداً صحيحاً موجباً.")

        try:
            duration = int(duree_totale_minutes)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "مدة الدرس يجب أن تكون عدداً صحيحاً موجباً."
            ) from exc

        if duration <= 0 or duration != duree_totale_minutes:
            raise ValueError(
                "مدة الدرس يجب أن تكون عدداً صحيحاً موجباً."
            )

        self.duree_totale = duration

    # --------------------------------------------------
    # 1. معالجة النصوص والبيانات
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
    def _as_list(cls, value: Any) -> List[str]:

        if value is None:
            return []

        if isinstance(value, str):

            parts = (
                value.replace("\r", "\n")
                .replace(";", "\n")
                .split("\n")
            )

            return [
                item.strip(" •-*\t\r")
                for item in parts
                if item.strip(" •-*\t\r")
            ]

        if isinstance(value, dict):
            value = [value]

        if isinstance(value, (list, tuple, set)):

            result = []

            for item in value:

                if isinstance(item, dict):
                    item = (
                        item.get("label_ar")
                        or item.get("label")
                        or item.get("name")
                        or item.get("value")
                        or item.get("detail")
                    )

                text = cls._text(item)

                if text and text not in result:
                    result.append(text)

            return result

        return []

    @classmethod
    def _get_field(
        cls,
        data: Dict[str, Any],
        field_name: str
    ) -> Any:

        for alias in cls.FIELD_ALIASES[field_name]:

            value = data.get(alias)

            if value is not None:
                return value

        return None

    @classmethod
    def _get_list(
        cls,
        data: Dict[str, Any],
        field_name: str
    ) -> List[str]:

        return cls._as_list(
            cls._get_field(data, field_name)
        )

    # --------------------------------------------------
    # 2. تحديد طبيعة العنصر ومصدره
    # --------------------------------------------------

    @classmethod
    def _is_modq_item(
        cls,
        competence: Dict[str, Any]
    ) -> bool:

        if competence.get("is_modq") is True:
            return True

        markers = [
            competence.get("item_type"),
            competence.get("type"),
            competence.get("category"),
            competence.get("source_group"),
            competence.get("group"),
            competence.get("origin"),
            competence.get("source"),
        ]

        for marker in markers:

            value = cls._text(marker).casefold()

            if "modq" in value:
                return True

        return False

    @classmethod
    def _source_status(
        cls,
        competence: Dict[str, Any],
        field_name: str = ""
    ) -> str:

        """
        لا تعتبر البيانات مرجعية إلا إذا صُرّح بمصدرها.
        """

        field_sources = competence.get("field_sources", {})

        if isinstance(field_sources, dict) and field_name:

            field_source = cls._text(
                field_sources.get(field_name)
            ).casefold()

            if field_source in {
                "rnfc",
                "référentiel",
                "referentiel",
                "مرجعي",
                "مرجعية",
            }:
                return "مرجعي RNFC؛ مع الاحتفاظ ببيانات المصدر"

            if field_source in {
                "proposed",
                "proposal",
                "مقترح",
            }:
                return "مقترح بيداغوجي"

            if field_source:
                return "بيانات مدخلة؛ مصدرها يحتاج إلى التحقق"

        source = cls._text(
            competence.get("source")
            or competence.get("provenance")
            or competence.get("data_source")
        ).casefold()

        if source in {
            "rnfc",
            "référentiel",
            "referentiel",
            "مرجعي",
            "مرجعية",
        }:
            return "مرجعي RNFC؛ مع الاحتفاظ ببيانات المصدر"

        if source in {"proposed", "proposal", "مقترح"}:
            return "مقترح بيداغوجي"

        return "بيانات مدخلة غير متحقق من مرجعيتها"

    # --------------------------------------------------
    # 3. توزيع الزمن
    # --------------------------------------------------

    def _allocate_phase_durations(self) -> List[int]:

        """
        توزيع مدة الحصة وفق النسب المحددة.
        مجموع الدقائق يساوي دائماً مدة الحصة.
        """

        raw = [
            self.duree_totale * pct / 100
            for _, _, pct in self.PHASES
        ]

        allocated = [int(value) for value in raw]

        remaining = self.duree_totale - sum(allocated)

        order = sorted(
            range(len(raw)),
            key=lambda i: (
                raw[i] - allocated[i],
                -i
            ),
            reverse=True
        )

        for index in order[:remaining]:
            allocated[index] += 1

        return allocated

    # --------------------------------------------------
    # 4. بناء شبكة التقييم
    # --------------------------------------------------

    @classmethod
    def _build_evaluation_grid(
        cls,
        competence: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], bool]:

        criteria = cls._get_list(
            competence,
            "criteria"
        )

        indicators = cls._get_list(
            competence,
            "indicators"
        )

        proposed = not bool(criteria)

        if proposed:
            selected = cls.DEFAULT_CRITERIA.copy()
        else:
            selected = criteria[:4]

        count = len(selected)

        weights_by_count = {
            1: [100],
            2: [60, 40],
            3: [50, 30, 20],
            4: [40, 30, 20, 10],
        }

        weights = weights_by_count[count]

        grid = []

        for index, (criterion, weight) in enumerate(
            zip(selected, weights)
        ):

            if index < len(indicators):
                indicator = indicators[index]
                indicator_source = cls._source_status(
                    competence,
                    "indicators"
                )
            else:
                indicator = (
                    "مؤشر مقترح يحدده الأستاذ "
                    "وفق طبيعة الأداء"
                )
                indicator_source = "مقترح بيداغوجي"

            grid.append({
                "critere": criterion,
                "poids_propose": weight,
                "indicateurs": indicator,
                "source": (
                    "مقترح بيداغوجي"
                    if proposed
                    else cls._source_status(
                        competence,
                        "criteria"
                    )
                ),
                "indicator_source": indicator_source,
            })

        return grid, proposed

    # --------------------------------------------------
    # 5. بناء محتوى التعلم
    # --------------------------------------------------

    def _build_course_content(
        self,
        competence: Dict[str, Any],
        resources: List[str],
        prerequisites: List[str],
        conditions: List[str]
    ) -> List[Dict[str, Any]]:

        content = []

        if prerequisites:

            content.append({
                "element": "المكتسبات القبلية",
                "detail": "؛ ".join(prerequisites),
                "source": self._source_status(
                    competence,
                    "prerequisites"
                ),
                "type": "prerequisite",
            })

        for index, resource in enumerate(resources, 1):

            content.append({
                "element": f"مورد تعلم {index}",
                "detail": resource,
                "source": self._source_status(
                    competence,
                    "resources"
                ),
                "type": "learning_resource",
            })

        if conditions:

            content.append({
                "element": "شروط الإنجاز",
                "detail": "؛ ".join(conditions),
                "source": self._source_status(
                    competence,
                    "conditions"
                ),
                "type": "execution_condition",
            })

        if not resources:

            content.append({
                "element": "الموارد",
                "detail": (
                    "يجب تحديد الموارد انطلاقاً من "
                    "وثائق التخصص المعتمدة."
                ),
                "source": "معلومات غير متوفرة",
                "type": "missing_resource",
            })

        return content

    # --------------------------------------------------
    # 6. بناء مراحل التعلم
    # --------------------------------------------------

    def _build_phases(
        self,
        name: str,
        description: str,
        resources: List[str],
        competence: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        durations = self._allocate_phase_durations()

        resource_text = (
            "؛ ".join(resources)
            if resources
            else "موارد التعلم التي يحددها الأستاذ"
        )

        phase_texts = [

            (
                f"وضعية مهنية مرتبطة بـ«{name}». "
                "يُطلب من المتكون تحليل المهمة وتحديد المطلوب.",
                "عرض الوضعية وشرح المهمة والقيود.",
                "تحليل الوضعية وتحديد المطلوب.",
            ),

            (
                f"تحديد الموارد اللازمة لإنجاز «{name}»: "
                f"{resource_text}",
                "توجيه المتكون إلى الموارد المتاحة.",
                "استحضار الموارد وتبرير اختيارها.",
            ),

            (
                f"التعلم والتطبيق الموجه للكفاءة «{name}». "
                f"الوصف المتاح: {description}",
                "تقديم الشرح أو البيان العملي ومرافقة التطبيق.",
                "إنجاز الأنشطة والتجريب وتسجيل النتائج.",
            ),

            (
                f"إنجاز مهمة إدماجية مرتبطة بـ«{name}» "
                "والتحقق من النتيجة.",
                "الملاحظة وجمع أدلة الأداء.",
                "إنجاز المهمة والتحقق من النتيجة.",
            ),

            (
                "معالجة النقائص المكتشفة ونقل التعلم "
                "إلى وضعية بديلة.",
                "تقديم التغذية الراجعة وأنشطة الدعم.",
                "تصحيح الأخطاء وإعادة توظيف المكتسبات.",
            ),
        ]

        phases = []

        for index, (
            phase_definition,
            phase_text,
            minutes
        ) in enumerate(
            zip(self.PHASES, phase_texts, durations),
            1
        ):

            title, title_fr, percentage = phase_definition

            scenario, trainer, learner = phase_text

            phases.append({

                "numero": index,

                "titre_ar": title,
                "titre_fr": title_fr,

                "duree_pct": percentage,
                "duree_min": minutes,

                "scenario": scenario,

                "role_formateur": trainer,
                "role_apprenant": learner,

                "productions_attendues": [
                    "أثر عمل أو إجابة أو منتج قابل للملاحظة"
                ],

                "source": "مقترح لتنظيم التعلم",

                "source_data": "بيانات العنصر المدخل",

            })

        return phases

    # --------------------------------------------------
    # 7. بناء مخطط الحصة
    # --------------------------------------------------

    def _build_course_plan(
        self,
        phases: List[Dict[str, Any]],
        resources: List[str],
        description: str
    ) -> List[Dict[str, Any]]:

        objectives = [

            "تحليل الوضعية وتحديد المهمة المطلوبة.",

            "تحديد الموارد الضرورية وتبرير اختيارها.",

            "تطبيق الموارد والإجراءات المرتبطة بالتعلم.",

            "إنجاز مهمة إدماجية والتحقق من نتيجتها.",

            "معالجة النقائص ونقل التعلم إلى وضعية جديدة.",
        ]

        plan = []

        for index, phase in enumerate(phases):

            if resources:
                associated = resources[
                    min(index, len(resources) - 1)
                ]
            else:
                associated = description

            plan.append({

                "etape": (
                    f"{index + 1}. {phase['titre_ar']}"
                ),

                "duree": (
                    f"{phase['duree_min']} دقيقة"
                ),

                "objectif": objectives[index],

                "activite_formateur": (
                    phase["role_formateur"]
                ),

                "activite_apprenant": (
                    phase["role_apprenant"]
                ),

                "contenu_associe": associated,

                "duree_pct": phase["duree_pct"],

                "source": "مقترح بيداغوجي",

            })

        return plan

    # --------------------------------------------------
    # 8. مراقبة جودة بطاقة التعلم
    # --------------------------------------------------

    def _quality_check(
        self,
        competence: Dict[str, Any],
        is_modq: bool,
    ) -> Dict[str, Any]:

        missing = []

        field_labels = {
            "resources": "الموارد",
            "criteria": "معايير الأداء",
            "indicators": "مؤشرات الأداء",
            "conditions": "شروط الإنجاز",
        }

        for field_name, label in field_labels.items():

            if not self._get_list(
                competence,
                field_name
            ):
                missing.append(label)

        warnings = []

        if is_modq:

            warnings.append(
                "هذا العنصر تابع لمجموعة modQ "
                "ولا يُعتبر كفاءة مهنية مثبتة."
            )

        if missing:

            warnings.append(
                "توجد بيانات ناقصة: "
                + "، ".join(missing)
            )

        if not self._get_list(
            competence,
            "prerequisites"
        ):

            warnings.append(
                "لم تُحدد مكتسبات قبلية مرجعية."
            )

        return {

            "is_complete": not bool(missing),

            "missing_fields": missing,

            "warnings": warnings,

            "requires_teacher_validation": True,

        }

    # --------------------------------------------------
    # 9. الواجهة الرئيسية للمحرك
    # --------------------------------------------------

    def generer_fiche(
        self,
        competence: Dict[str, Any]
    ) -> Dict[str, Any]:

        if not isinstance(competence, dict):

            raise TypeError(
                "يجب أن تكون بيانات العنصر قاموساً."
            )

        name = self._text(
            competence.get("label_ar")
            or competence.get("label")
            or competence.get("label_fr")
            or competence.get("nom"),
            "عنصر غير معنّون"
        )

        code = self._text(
            competence.get("code"),
            "غير محدد"
        )

        description = self._text(
            competence.get("description")
            or competence.get("description_ar"),
            name
        )

        # تحديد طبيعة العنصر
        is_modq = self._is_modq_item(competence)

        if is_modq:
            item_classification = "عنصر من modQ"
            item_status = "غير مثبت ككفاءة مهنية"
        else:
            item_classification = self._text(
                competence.get("classification"),
                "عنصر تعلم يحتاج إلى التحقق من تصنيفه"
            )
            item_status = self._text(
                competence.get("validation_status"),
                "غير متحقق من الاعتماد المرجعي"
            )

        resources = self._get_list(
            competence,
            "resources"
        )

        prerequisites = self._get_list(
            competence,
            "prerequisites"
        )

        conditions = self._get_list(
            competence,
            "conditions"
        )

        # بناء المكونات
        phases = self._build_phases(
            name,
            description,
            resources,
            competence
        )

        grid, criteria_proposed = (
            self._build_evaluation_grid(competence)
        )

        content = self._build_course_content(
            competence,
            resources,
            prerequisites,
            conditions
        )

        plan = self._build_course_plan(
            phases,
            resources,
            description
        )

        quality = self._quality_check(
            competence,
            is_modq
        )

        # المخرجات المتوافقة مع app.py
        result = {

            "competence": {

                "code": code,
                "nom": name,
                "description": description,

                "classification": item_classification,

                "validation_status": item_status,

                "is_modq": is_modq,

            },

            "objectif_intermediaire": (
                f"أن ينجز المتكون المهمة المرتبطة بـ«{name}» "
                "وفق شروط الإنجاز ومعايير التقييم "
                "التي يصادق عليها الأستاذ."
            ),

            "buts_partiels": [

                {
                    "numero": 1,

                    "but_partiel": (
                        "تحليل المهمة وتحديد الموارد اللازمة"
                    ),

                    "indicateur": (
                        "تحديد المطلوب والموارد بصورة مبررة"
                    ),

                    "source": "مقترح بيداغوجي",
                },

                {
                    "numero": 2,

                    "but_partiel": (
                        "إنجاز المهمة والتحقق من جودتها"
                    ),

                    "indicateur": (
                        "نتيجة قابلة للملاحظة والتحقق"
                    ),

                    "source": "مقترح بيداغوجي",
                },

            ],

            "prerequisites": prerequisites,

            "conditions": conditions,

            "phases": phases,

            "grille_evaluation": grid,

            "plan_cours": plan,

            "contenu_cours": content,

            "duration_minutes": self.duree_totale,

            "quality_notes": quality["warnings"],

            # بيانات إضافية للمراحل اللاحقة
            "metadata": {

                "engine": "APCEngine",

                "version": "2.0",

                "item_type": item_classification,

                "is_modq": is_modq,

                "reference_status": item_status,

                "criteria_proposed": criteria_proposed,

                "teacher_validation_required": True,

            },

            "quality_report": quality,

            "logigramme_input": {

                "code": code,

                "label": name,

                "item_type": item_classification,

                "is_modq": is_modq,

                "prerequisites": prerequisites,

                "resources": resources,

                "conditions": conditions,

                "phases": phases,

                "criteria": grid,

                "duration_minutes": self.duree_totale,

            },

        }

        return result


# ------------------------------------------------------
# توافق إضافي مع الاستدعاء المباشر للمحرك
# ------------------------------------------------------

def generer_fiche(
    competence: Dict[str, Any],
    duree_totale_minutes: int = 120
) -> Dict[str, Any]:

    engine = APCEngine(duree_totale_minutes)

    return engine.generer_fiche(competence)
