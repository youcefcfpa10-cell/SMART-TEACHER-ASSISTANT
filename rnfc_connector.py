
# -*- coding: utf-8 -*-
"""موصل RNFC — حفظ الحقول الأصلية وتحليل البيانات دون اختراع معلومات."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


# الحقول الأصلية المعتمدة في ملف RNFC.
# يجب عدم تغيير أسمائها أو إضافة أعمدة مفترضة إليها.
RNFC_FIELDS = [
    "specialite_id",
    "codnom",
    "id_sdom",
    "nom",
    "nom_spe_ar",
    "type_form",
    "type_form_ar",
    "id_inst",
    "nivq",
    "diplom",
    "diplom_ar",
    "object",
    "object_ar",
    "duree",
    "duree_ar",
    "nivSc",
    "nivSC_ar",
    "modFor",
    "modFor_ar",
    "debou",
    "debou_ar",
    "modQ",
    "modQ_ar",
    "modc",
    "modc_ar",
    "def",
    "def_ar",
    "appel",
    "appel_ar",
    "exig",
    "exig_ar",
    "listcqp",
    "listcqp_ar",
    "evol",
    "evol_ar",
    "modeval",
    "modeval_ar",
    "nom_sdomaine_fr",
    "nom_sdomaine_ar",
    "nom_domaine_fr",
    "nom_domaine_ar",
    "nom_secteur_fr",
    "nom_secteur_ar",
    "id_sect",
    "id_dom",
]


# الحقول الثنائية اللغة.
PAIRED_FIELDS = {
    "type_formation": ("type_form_ar", "type_form"),
    "diplome": ("diplom_ar", "diplom"),
    "objectif_reference": ("object_ar", "object"),
    "duree": ("duree_ar", "duree"),
    "niveau_scolaire": ("nivSC_ar", "nivSc"),
    "mode_formation": ("modFor_ar", "modFor"),
    "debouches": ("debou_ar", "debou"),
    "definition_metier": ("def_ar", "def"),
    "appellations_metier": ("appel_ar", "appel"),
    "conditions_acces": ("exig_ar", "exig"),
    "evolution_reglementaire": ("evol_ar", "evol"),
    "modalites_evaluation": ("modeval_ar", "modeval"),
}


KNOWN_SHEETS = [
    "المتوج بشهادة",
    "عبر المعابر",
    "تاهيلي أولي",
]


class RNFCConnectorError(RuntimeError):
    """خطأ خاص بقراءة مرجع RNFC."""


class RNFCConnector:

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()

    # --------------------------------------------------------
    # اكتشاف ملف المرجع
    # --------------------------------------------------------

    def _find_rnfc_file(self) -> Optional[Path]:

        if not self.data_dir.exists():
            return None

        supported = {".xlsx", ".xls", ".json"}

        files = [
            p for p in self.data_dir.iterdir()
            if p.is_file() and p.suffix.lower() in supported
        ]

        if not files:
            return None

        named = [
            p for p in files
            if p.stem.casefold().startswith("rnfc")
        ]

        if len(named) == 1:
            return named[0]

        if len(named) > 1:
            raise RNFCConnectorError(
                "تم العثور على أكثر من ملف يبدأ اسمه بـ RNFC. "
                "يرجى الإبقاء على ملف مرجعي واحد داخل مجلد data."
            )

        if len(files) == 1:
            return files[0]

        raise RNFCConnectorError(
            "يوجد أكثر من ملف Excel أو JSON داخل مجلد data "
            "ولا يوجد ملف محدد يبدأ اسمه بـ RNFC. "
            "يرجى تسمية ملف المرجع RNFC.xlsx."
        )

    # --------------------------------------------------------
    # تنظيف القيم
    # --------------------------------------------------------

    @staticmethod
    def _clean(value: Any) -> str:

        if value is None:
            return ""

        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass

        text = str(value).replace("\x00", "").strip()

        if text.casefold() in {"nan", "none", "null", "nat"}:
            return ""

        return text

    @classmethod
    def _lines(cls, value: Any) -> List[str]:
        """استخراج عناصر الحقل النصي دون إسقاط العناصر الزائدة."""

        text = cls._clean(value)

        if not text or text.strip() in {"/", "-"}:
            return []

        normalized = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        result: List[str] = []

        for raw in normalized.split("\n"):

            line = raw.strip().lstrip(
                "•▪*-–— \t"
            ).strip()

            if line and line not in {"/", "-"}:
                if line not in result:
                    result.append(line)

        return result

    @classmethod
    def _paired_text(
        cls,
        row: Dict[str, Any],
        arabic: str,
        french: str,
    ) -> Dict[str, str]:

        return {
            "ar": cls._clean(row.get(arabic)),
            "fr": cls._clean(row.get(french)),
        }

    @classmethod
    def _pair_lists(
        cls,
        arabic_values: List[str],
        french_values: List[str],
    ) -> List[Tuple[str, str]]:

        count = max(
            len(arabic_values),
            len(french_values),
        )

        return [
            (
                arabic_values[i] if i < len(arabic_values) else "",
                french_values[i] if i < len(french_values) else "",
            )
            for i in range(count)
        ]

    # --------------------------------------------------------
    # أسماء الأوراق
    # --------------------------------------------------------

    def get_sheet_names(self) -> List[str]:

        path = self._find_rnfc_file()

        if not path or path.suffix.lower() == ".json":
            return []

        try:
            with pd.ExcelFile(path) as excel:
                return list(excel.sheet_names)

        except Exception as exc:
            raise RNFCConnectorError(
                f"تعذر قراءة أوراق Excel: {exc}"
            ) from exc

    # --------------------------------------------------------
    # فحص بنية الأعمدة
    # --------------------------------------------------------

    @staticmethod
    def _schema_report(columns: List[str]) -> Dict[str, Any]:

        actual = set(columns)
        expected = set(RNFC_FIELDS)

        missing = [
            field for field in RNFC_FIELDS
            if field not in actual
        ]

        extra = [
            field for field in columns
            if field not in expected
        ]

        return {
            "expected_count": len(RNFC_FIELDS),
            "actual_count": len(columns),
            "missing_fields": missing,
            "extra_fields": extra,
            "is_complete": not missing and not extra,
        }

    # --------------------------------------------------------
    # إنشاء عناصر modQ
    # --------------------------------------------------------

    def _build_modq_elements(
        self,
        row: Dict[str, Any],
        specialite_id: str,
    ) -> List[Dict[str, Any]]:

        arabic_values = self._lines(
            row.get("modQ_ar")
        )

        french_values = self._lines(
            row.get("modQ")
        )

        pairs = self._pair_lists(
            arabic_values,
            french_values,
        )

        elements = []

        for index, (ar, fr) in enumerate(pairs, 1):

            elements.append({
                "id": f"{specialite_id}-MQ-{index:02d}",
                "code": f"MQ-{index:02d}",

                "label": ar or fr,
                "label_ar": ar,
                "label_fr": fr,

                "description": ar or fr,

                "element_type": "modQ",
                "element_classification": (
                    "عنصر تأهيلي وارد في المرجع"
                ),

                "source_field": (
                    "modQ_ar + modQ"
                    if ar and fr
                    else "modQ_ar"
                    if ar
                    else "modQ"
                ),

                "source_status": (
                    "مرجعي: مستخرج من الحقل الأصلي في RNFC"
                ),

                "source_origin": "RNFC",
                "is_reference": True,
                "is_inferred": False,
                "is_proposed": False,

                # لا توجد علاقة قبلية مثبتة في هذا الحقل.
                "prerequisites": [],
                "prerequisites_source": (
                    "غير محددة في البيانات المتاحة"
                ),
            })

        return elements

    # --------------------------------------------------------
    # استخراج عناصر modc و listcqp
    # --------------------------------------------------------

    def _build_reference_list(
        self,
        row: Dict[str, Any],
        arabic_field: str,
        french_field: str,
        category: str,
    ) -> List[Dict[str, Any]]:

        arabic_values = self._lines(
            row.get(arabic_field)
        )

        french_values = self._lines(
            row.get(french_field)
        )

        pairs = self._pair_lists(
            arabic_values,
            french_values,
        )

        result = []

        for index, (ar, fr) in enumerate(pairs, 1):

            result.append({
                "id": f"{category}-{index:02d}",
                "label": ar or fr,
                "label_ar": ar,
                "label_fr": fr,

                "category": category,

                "source_field": (
                    f"{arabic_field} + {french_field}"
                    if ar and fr
                    else arabic_field
                    if ar
                    else french_field
                ),

                "source_status": (
                    "مرجعي: مستخرج حرفياً من ملف RNFC"
                ),

                "source_origin": "RNFC",
                "is_reference": True,
                "is_inferred": False,
                "is_proposed": False,
            })

        return result

    # --------------------------------------------------------
    # تحويل صف Excel إلى سجل تخصص
    # --------------------------------------------------------

    def _build_specialite(
        self,
        row: Dict[str, Any],
        row_index: int,
        sheet_name: str,
    ) -> Dict[str, Any]:

        specialite_id = (
            self._clean(row.get("specialite_id"))
            or f"ROW-{row_index + 1}"
        )

        code = self._clean(
            row.get("codnom")
        )

        name_ar = self._clean(
            row.get("nom_spe_ar")
        )

        name_fr = self._clean(
            row.get("nom")
        )

        if not name_ar and not name_fr:
            name_ar = "تخصص غير معنون"

        # الاحتفاظ بجميع الحقول الأصلية الـ45.
        raw_fields = {
            field: self._clean(row.get(field))
            for field in RNFC_FIELDS
        }

        # العناصر الموجودة في modQ.
        elements = self._build_modq_elements(
            row,
            specialite_id,
        )

        # محتويات modc تبقى مستقلة دون افتراض معناها.
        modc_items = self._build_reference_list(
            row,
            "modc_ar",
            "modc",
            "modc",
        )

        # محتويات listcqp تبقى مستقلة.
        cqp_items = self._build_reference_list(
            row,
            "listcqp_ar",
            "listcqp",
            "listcqp",
        )

        secteur = {
            "id": self._clean(row.get("id_sect")),
            "label": self._clean(
                row.get("nom_secteur_ar")
            ) or self._clean(row.get("nom_secteur_fr")) or "—",
            "label_ar": self._clean(
                row.get("nom_secteur_ar")
            ),
            "label_fr": self._clean(
                row.get("nom_secteur_fr")
            ),
        }

        domaine = {
            "id": self._clean(row.get("id_dom")),
            "label": self._clean(
                row.get("nom_domaine_ar")
            ) or self._clean(row.get("nom_domaine_fr")) or "—",
            "label_ar": self._clean(
                row.get("nom_domaine_ar")
            ),
            "label_fr": self._clean(
                row.get("nom_domaine_fr")
            ),
        }

        sous_domaine = {
            "id": self._clean(row.get("id_sdom")),
            "label": self._clean(
                row.get("nom_sdomaine_ar")
            ) or self._clean(row.get("nom_sdomaine_fr")) or "—",
            "label_ar": self._clean(
                row.get("nom_sdomaine_ar")
            ),
            "label_fr": self._clean(
                row.get("nom_sdomaine_fr")
            ),
        }

        paired = {
            key: self._paired_text(
                row,
                arabic_field,
                french_field,
            )
            for key, (arabic_field, french_field)
            in PAIRED_FIELDS.items()
        }

        return {
            # الهوية والتسمية.
            "id": specialite_id,
            "code": code,
            "label": name_fr or name_ar,
            "label_ar": name_ar,
            "label_fr": name_fr,

            # البيانات التنظيمية.
            "id_inst": raw_fields["id_inst"],
            "nivq": raw_fields["nivq"],

            "type_formation": paired["type_formation"],
            "diplome": paired["diplome"],
            "objectif_reference": paired["objectif_reference"],
            "duree": paired["duree"],
            "niveau_scolaire": paired["niveau_scolaire"],
            "mode_formation": paired["mode_formation"],
            "debouches": paired["debouches"],

            "definition_metier": paired["definition_metier"],
            "appellations_metier": paired["appellations_metier"],
            "conditions_acces": paired["conditions_acces"],
            "evolution_reglementaire": paired["evolution_reglementaire"],
            "modalites_evaluation": paired["modalites_evaluation"],

            # التصنيف المهني.
            "secteur": secteur,
            "domaine": domaine,
            "sous_domaine": sous_domaine,

            # عناصر modQ.
            "elements_qualification": elements,

            # توافق خلفي مع التطبيق الحالي.
            # هذه عناصر modQ وليست كفاءات مهنية مثبتة.
            "competences": elements,

            # الاحتفاظ بـ modc و listcqp منفصلين.
            "elements_modc": modc_items,
            "ressources_complementaires": modc_items,

            "elements_listcqp": cqp_items,
            "competences_professionnelles_cqp": cqp_items,

            # الأهداف المرجعية.
            "objectifs_reference": self._lines(
                row.get("object_ar")
            ) or self._lines(row.get("object")),

            # البيانات الخام الأصلية.
            "rnfc_fields": raw_fields,

            # معلومات المصدر.
            "source_origin": "RNFC",
            "source_sheet": sheet_name,
            "source_row": row_index + 2,

            "reference_status": (
                "بيانات مستخرجة من المرجع الأصلي"
            ),

            "reference_warnings": (
                []
                if elements
                else [
                    "الحقل modQ لا يحتوي على عناصر قابلة للاستخراج."
                ]
            ),

            # بيانات التحليل لم تُنشأ بعد.
            "analysis_status": "لم يبدأ التحليل",
            "inferred_competences": [],
            "proposed_competences": [],
        }

    # --------------------------------------------------------
    # قراءة Excel
    # --------------------------------------------------------

    def _from_excel(
        self,
        path: Path,
        sheet_name: Optional[str],
    ) -> Dict[str, Any]:

        try:

            with pd.ExcelFile(path) as excel:

                available_sheets = list(
                    excel.sheet_names
                )

                if not available_sheets:
                    raise RNFCConnectorError(
                        "ملف Excel لا يحتوي على أوراق عمل."
                    )

                if sheet_name:

                    if sheet_name not in available_sheets:
                        raise RNFCConnectorError(
                            f"ورقة Excel المطلوبة غير موجودة: {sheet_name}. "
                            f"الأوراق المتاحة: {', '.join(available_sheets)}"
                        )

                    chosen_sheet = sheet_name

                else:

                    matching = [
                        name for name in KNOWN_SHEETS
                        if name in available_sheets
                    ]

                    if len(matching) == 1:
                        chosen_sheet = matching[0]

                    elif len(available_sheets) == 1:
                        chosen_sheet = available_sheets[0]

                    else:
                        raise RNFCConnectorError(
                            "يحتوي ملف Excel على عدة أوراق. "
                            "يرجى تحديد ورقة العمل المطلوبة."
                        )

                df = pd.read_excel(
                    excel,
                    sheet_name=chosen_sheet,
                    dtype=object,
                )

        except RNFCConnectorError:
            raise

        except Exception as exc:
            raise RNFCConnectorError(
                f"تعذر قراءة ملف Excel: {exc}"
            ) from exc

        # تنظيف أسماء الأعمدة فقط، دون إعادة تسميتها.
        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        if df.columns.duplicated().any():

            duplicates = [
                str(column)
                for column in df.columns[
                    df.columns.duplicated()
                ]
            ]

            raise RNFCConnectorError(
                "توجد أسماء أعمدة مكررة في ملف RNFC: "
                + "، ".join(duplicates)
            )

        schema = self._schema_report(
            list(df.columns)
        )

        missing_identity = [
            field for field in ("specialite_id", "codnom")
            if field in schema["missing_fields"]
        ]

        if missing_identity:

            raise RNFCConnectorError(
                "لا يمكن تحديد التخصصات بسبب غياب حقول الهوية: "
                + "، ".join(missing_identity)
            )

        if df.empty:

            raise RNFCConnectorError(
                f"ورقة RNFC فارغة: {chosen_sheet}"
            )

        specialites = []

        for row_index, series in df.iterrows():

            row = {
                str(key): value
                for key, value in series.to_dict().items()
            }

            # تجاهل الصفوف الفارغة تماماً.
            if not any(
                self._clean(row.get(field))
                for field in RNFC_FIELDS
            ):
                continue

            specialites.append(
                self._build_specialite(
                    row,
                    int(row_index),
                    chosen_sheet,
                )
            )

        if not specialites:

            raise RNFCConnectorError(
                "لم يتم العثور على سجلات تخصص صالحة في الورقة المحددة."
            )

        # كشف المعرفات المكررة دون حذف البيانات.
        ids = [
            item["id"]
            for item in specialites
        ]

        duplicate_ids = sorted({
            value for value in ids
            if ids.count(value) > 1
        })

        stats = {
            "specialites": len(specialites),

            "elements_qualification": sum(
                len(item["elements_qualification"])
                for item in specialites
            ),

            "competences": sum(
                len(item["competences"])
                for item in specialites
            ),

            "elements_modc": sum(
                len(item["elements_modc"])
                for item in specialites
            ),

            "competences_professionnelles_cqp": sum(
                len(item["competences_professionnelles_cqp"])
                for item in specialites
            ),
        }

        return {
            "source": str(path),
            "sheet": chosen_sheet,
            "schema_version": "5.0",

            "schema": schema,

            "stats": stats,

            "specialites": specialites,

            "validation": {
                "is_schema_complete": schema["is_complete"],
                "duplicate_specialite_ids": duplicate_ids,
                "has_duplicate_ids": bool(duplicate_ids),
            },

            "source_policy": {
                "original_fields_preserved": True,
                "original_field_names_changed": False,
                "missing_fields_fabricated": False,
                "prerequisites_invented": False,
                "reference_competences_invented": False,
            },
        }

    # --------------------------------------------------------
    # قراءة JSON
    # --------------------------------------------------------

    def _from_json(self, path: Path) -> Dict[str, Any]:

        try:

            with path.open(
                "r",
                encoding="utf-8-sig",
            ) as file:

                payload = json.load(file)

            if not isinstance(payload, dict):
                raise ValueError(
                    "يجب أن تكون بنية JSON قاموساً."
                )

            if not isinstance(
                payload.get("specialites"),
                list,
            ):
                raise ValueError(
                    "يلزم وجود specialites من نوع list."
                )

            payload.setdefault(
                "source",
                str(path),
            )

            payload.setdefault(
                "schema_version",
                "5.0",
            )

            payload.setdefault(
                "stats",
                {
                    "specialites": len(
                        payload["specialites"]
                    )
                },
            )

            return payload

        except Exception as exc:

            raise RNFCConnectorError(
                f"تعذر قراءة ملف JSON: {exc}"
            ) from exc

    # --------------------------------------------------------
    # الواجهة العامة
    # --------------------------------------------------------

    def load_data(
        self,
        sheet_name: str = "المتوج بشهادة",
    ) -> Dict[str, Any]:

        path = self._find_rnfc_file()

        if not path:

            raise RNFCConnectorError(
                f"لم يتم العثور على ملف RNFC داخل:\n"
                f"{self.data_dir}\n"
                "ضع ملف Excel المرجعي داخل مجلد data."
            )

        extension = path.suffix.lower()

        if extension in {".xlsx", ".xls"}:

            return self._from_excel(
                path,
                sheet_name,
            )

        if extension == ".json":
            return self._from_json(path)

        raise RNFCConnectorError(
            f"امتداد الملف غير مدعوم: {extension}"
        )


# ------------------------------------------------------------
# البحث عن التخصصات
# ------------------------------------------------------------

def search_specialites(
    payload: Dict[str, Any],
    query: str = "",
) -> List[Dict[str, Any]]:

    items = payload.get(
        "specialites",
        [],
    )

    q = str(query or "").strip().casefold()

    if not q:
        return items

    results = []

    for item in items:

        searchable = [
            item.get("label", ""),
            item.get("label_ar", ""),
            item.get("label_fr", ""),
            item.get("code", ""),
            item.get("id", ""),
        ]

        searchable_text = " ".join(
            str(value)
            for value in searchable
            if value is not None
        ).casefold()

        if q in searchable_text:
            results.append(item)

    return results


# ------------------------------------------------------------
# أدوات مساعدة للتحقق من المرجع
# ------------------------------------------------------------

def get_rnfc_schema() -> List[str]:
    """إرجاع قائمة الحقول الأصلية المعتمدة."""
    return RNFC_FIELDS.copy()


def validate_specialite_record(
    specialite: Dict[str, Any],
) -> Dict[str, Any]:

    raw = specialite.get(
        "rnfc_fields",
        {},
    )

    missing = [
        field for field in RNFC_FIELDS
        if field not in raw
    ]

    empty = [
        field for field in RNFC_FIELDS
        if field in raw and not str(raw.get(field, "")).strip()
    ]

    return {
        "is_complete": not missing,
        "missing_fields": missing,
        "empty_fields": empty,
        "original_fields_count": len(raw),
        "expected_fields_count": len(RNFC_FIELDS),
    }
