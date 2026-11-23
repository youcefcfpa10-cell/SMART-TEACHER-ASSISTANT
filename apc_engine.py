# -*- coding: utf-8 -*-
"""محرك إعداد بطاقات التعلم وفق المقاربة بالكفاءات APC.

لا ينسب المحرك إلى RNFC أي محتوى غير موجود في البيانات المدخلة.
العناصر العامة المضافة آلياً موسومة بأنها مقترحات تحتاج إلى مصادقة الأستاذ.
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

    def __init__(self, duree_totale_minutes: int = 120) -> None:
        if isinstance(duree_totale_minutes, bool):
            raise ValueError("مدة الدرس يجب أن تكون عدداً صحيحاً موجباً بالدقائق.")
        try:
            duration = int(duree_totale_minutes)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("مدة الدرس يجب أن تكون عدداً صحيحاً موجباً بالدقائق.") from exc
        if duration <= 0 or duration != duree_totale_minutes:
            raise ValueError("مدة الدرس يجب أن تكون عدداً صحيحاً موجباً بالدقائق.")
        self.duree_totale = duration

    @staticmethod
    def _text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return default if text.casefold() in {"", "nan", "none", "null"} else text

    @classmethod
    def _as_list(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = value.replace("\r", "\n").replace(";", "\n").split("\n")
            return [x.strip(" •-*\t\r") for x in parts if x.strip(" •-*\t\r")]
        if isinstance(value, (list, tuple, set)):
            result: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    item = item.get("label_ar") or item.get("label") or item.get("name") or item.get("value") or item.get("detail")
                text = cls._text(item)
                if text and text not in result:
                    result.append(text)
            return result
        return []

    def _allocate_phase_durations(self) -> List[int]:
        """توزيع صحيح بالدقائق مع ضمان أن المجموع يساوي مدة الحصة تماماً."""
        raw = [self.duree_totale * pct / 100 for _, _, pct in self.PHASES]
        allocated = [int(x) for x in raw]
        remaining = self.duree_totale - sum(allocated)
        # أكبر البواقي أولاً؛ يحافظ على النسب ويمنع ضياع الدقائق بسبب التقريب.
        order = sorted(range(len(raw)), key=lambda i: (raw[i] - allocated[i], -i), reverse=True)
        for i in order[:remaining]:
            allocated[i] += 1
        return allocated

    def _generate_contextual_scenario(
        self, comp_nom: str, comp_desc: str, competence: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        resources = self._as_list(
            competence.get("resources") or competence.get("ressources") or competence.get("savoirs")
        )
        prerequisites = self._as_list(competence.get("prerequisites") or competence.get("prerequis"))
        criteria = self._as_list(competence.get("criteria") or competence.get("criteres"))
        indicators = self._as_list(competence.get("indicators") or competence.get("indicateurs"))
        conditions = self._as_list(competence.get("conditions") or competence.get("conditions_realisation"))

        has_reference_data = bool(resources or criteria or indicators or conditions or prerequisites)
        source_note = (
            "بيانات مرجعية/مدخلة؛ يلزم التحقق من حقل المصدر"
            if has_reference_data
            else "مقترح بيداغوجي عام؛ يلزم تخصيصه والتحقق منه وفق RNFC"
        )
        if not resources:
            resources = ["تحديد المعارف والوسائل التقنية اللازمة انطلاقاً من وثائق التخصص المعتمدة"]
        if not criteria:
            criteria = self.DEFAULT_CRITERIA.copy()
        if not indicators:
            indicators = ["مؤشر قابل للملاحظة والقياس يحدده الأستاذ وفق طبيعة الأداء"]

        problem = (
            f"في سياق مهني مرتبط بالتخصص، يُسند إلى المتكون طلب إنجاز مهمة تتطلب توظيف الكفاءة «{comp_nom}». "
            "يتعين عليه تحليل الطلب، وتحديد الموارد المناسبة، وتنفيذ العمل، ثم التحقق من النتيجة وفق الشروط المتاحة."
        )
        phase_texts = [
            (problem, "عرض الوضعية وشرح المطلوب دون تقديم الحل", "تحليل الوضعية وتحديد المطلوب والقيود"),
            (f"تحديد الموارد اللازمة لإنجاز «{comp_nom}»: " + "؛ ".join(resources),
             "توجيه المتكون إلى مصادر التعلم والموارد المعتمدة", "استحضار الموارد المتاحة وتبرير اختيارها"),
            (f"تعلم وتطبيق إجراءات الكفاءة «{comp_nom}» وفق الوصف المتاح: {comp_desc}",
             "تقديم الشرح أو البيان العملي ومرافقة التطبيق", "إنجاز الأنشطة والتجريب وتسجيل النتائج"),
            (f"إنجاز مهمة إدماجية مرتبطة بـ«{comp_nom}» وتقديم أدلة تحقق معايير الأداء",
             "الملاحظة وجمع أدلة الأداء وتطبيق شبكة التقييم", "إنجاز المهمة والتحقق من النتيجة وتبرير الاختيارات"),
            ("معالجة النقائص التي كشفت عنها نتائج التقييم، ثم نقل التعلم إلى وضعية بديلة",
             "تقديم تغذية راجعة وأنشطة دعم أو وضعية نقل", "تصحيح الأخطاء وإعادة توظيف المكتسبات في سياق جديد"),
        ]

        durations = self._allocate_phase_durations()
        phases: List[Dict[str, Any]] = []
        for i, ((title, title_fr, pct), (scenario, trainer, learner), minutes) in enumerate(
            zip(self.PHASES, phase_texts, durations), 1
        ):
            phases.append({
                "numero": i, "titre_ar": title, "titre_fr": title_fr,
                "duree_pct": pct, "duree_min": minutes,
                "scenario": scenario, "role_formateur": trainer,
                "role_apprenant": learner,
                "productions_attendues": ["أثر عمل أو إجابة أو منتج قابل للملاحظة"],
                "source": source_note,
            })

        # المعايير المرجعية لا تُستكمل بمعايير مقترحة داخل الشبكة نفسها.
        # إذا كانت البيانات ناقصة، نعرض شبكة مقترحة مستقلة بوسم واضح.
        criteria_are_proposed = not bool(self._as_list(competence.get("criteria") or competence.get("criteres")))
        chosen_criteria = (self.DEFAULT_CRITERIA if criteria_are_proposed else criteria[:4])
        weights = self.DEFAULT_WEIGHTS[:len(chosen_criteria)]
        if len(chosen_criteria) == 1:
            weights = [100]
        elif len(chosen_criteria) == 2:
            weights = [60, 40]
        elif len(chosen_criteria) == 3:
            weights = [50, 30, 20]
        elif len(chosen_criteria) == 4:
            weights = [40, 30, 20, 10]
        grille: List[Dict[str, Any]] = []
        for i, (criterion, weight) in enumerate(zip(chosen_criteria, weights)):
            indicator = indicators[i] if i < len(indicators) else "يحدده الأستاذ وفق طبيعة الأداء"
            grille.append({
                "critere": criterion,
                "poids_propose": weight,
                "indicateurs": indicator,
                "source": "مقترح" if criteria_are_proposed else "بيانات مدخلة؛ تحقق من مرجعيتها",
            })

        course_content = [
            {"element": f"مورد {i + 1}", "detail": item,
             "source": "بيانات مدخلة؛ تحقق من مصدرها" if has_reference_data else "مقترح"}
            for i, item in enumerate(resources)
        ]
        if prerequisites:
            course_content.insert(0, {
                "element": "المكتسبات القبلية", "detail": "؛ ".join(prerequisites),
                "source": "بيانات مدخلة؛ تحقق من مصدرها",
            })
        if conditions:
            course_content.append({
                "element": "شروط الإنجاز", "detail": "؛ ".join(conditions),
                "source": "بيانات مدخلة؛ تحقق من مصدرها",
            })

        objectives = [
            "تحليل وضعية مهنية وتحديد المهمة وشروط إنجازها.",
            "تحديد الموارد الضرورية وتبرير اختيارها.",
            "تطبيق الموارد والإجراءات المرتبطة بالكفاءة.",
            "إنجاز مهمة إدماجية والتحقق من مطابقتها للمعايير.",
            "معالجة النقائص ونقل التعلم إلى وضعية جديدة.",
        ]
        plan: List[Dict[str, Any]] = []
        for i, (phase, objective) in enumerate(zip(phases, objectives)):
            associated = resources[min(i, len(resources) - 1)] if resources else comp_desc
            plan.append({
                "etape": f"{i + 1}. {phase['titre_ar']}",
                "duree": f"{phase['duree_min']} دقيقة",
                "objectif": objective,
                "activite_formateur": phase["role_formateur"],
                "activite_apprenant": phase["role_apprenant"],
                "contenu_associe": associated,
                "duree_pct": phase["duree_pct"],
            })
        return phases, grille, plan, course_content

    def generer_fiche(self, competence: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(competence, dict):
            raise TypeError("يجب أن تكون بيانات الكفاءة قاموساً.")
        name = self._text(
            competence.get("label_ar") or competence.get("label") or competence.get("label_fr"),
            "كفاءة غير معنونة",
        )
        code = self._text(competence.get("code"), "غير محدد")
        desc = self._text(competence.get("description") or competence.get("description_ar"), name)
        phases, grille, plan, content = self._generate_contextual_scenario(name, desc, competence)
        missing = []
        if not self._as_list(competence.get("resources") or competence.get("ressources") or competence.get("savoirs")):
            missing.append("الموارد")
        if not self._as_list(competence.get("criteria") or competence.get("criteres")):
            missing.append("معايير الأداء")
        if not self._as_list(competence.get("indicators") or competence.get("indicateurs")):
            missing.append("مؤشرات الأداء")
        if not self._as_list(competence.get("conditions") or competence.get("conditions_realisation")):
            missing.append("شروط الإنجاز")
        return {
            "competence": {"code": code, "nom": name, "description": desc},
            "objectif_intermediaire": f"أن ينجز المتكون المهمة المرتبطة بـ«{name}» وفق شروط ومعايير الأداء المحددة.",
            "buts_partiels": [
                {"numero": 1, "but_partiel": "تحليل المهمة وتحديد الموارد اللازمة", "indicateur": "تحديد المطلوب والموارد بصورة مبررة"},
                {"numero": 2, "but_partiel": "إنجاز المهمة والتحقق من جودتها", "indicateur": "نتيجة قابلة للملاحظة ومطابقة للمعايير"},
            ],
            "prerequisites": self._as_list(competence.get("prerequisites") or competence.get("prerequis")),
            "conditions": self._as_list(competence.get("conditions") or competence.get("conditions_realisation")),
            "phases": phases, "grille_evaluation": grille,
            "plan_cours": plan, "contenu_cours": content,
            "duration_minutes": self.duree_totale,
            "quality_notes": (["بيانات غير متوفرة وتحتاج إلى استكمال من المرجع أو وثائق التخصص: " + "، ".join(missing) + "."] if missing else []),
        }
