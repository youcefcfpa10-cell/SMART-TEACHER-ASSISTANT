# -*- coding: utf-8 -*-
"""موصل مرجع RNFC: يحافظ على التمييز بين حقول المرجع ولا ينشئ بيانات غير موثقة."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


class RNFCConnectorError(RuntimeError):
    pass


class RNFCConnector:
    """قراءة أوراق RNFC مع الاحتفاظ بالمصدر العربي والفرنسي لكل حقل."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()

    def _find_rnfc_file(self) -> Optional[Path]:
        if not self.data_dir.exists():
            return None
        files = [p for p in self.data_dir.iterdir()
                 if p.is_file() and p.suffix.lower() in {".xlsx", ".xls", ".json"}]
        if not files:
            return None
        files.sort(key=lambda p: (0 if p.stem.casefold().startswith("rnfc") else 1, p.name.casefold()))
        return files[0]

    def get_sheet_names(self) -> List[str]:
        path = self._find_rnfc_file()
        if not path or path.suffix.lower() == ".json":
            return []
        try:
            with pd.ExcelFile(path) as excel:
                return list(excel.sheet_names)
        except Exception as exc:
            raise RNFCConnectorError(f"تعذر قراءة أوراق Excel: {exc}") from exc

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
        return "" if text.casefold() in {"nan", "none", "null"} else text

    @classmethod
    def _lines(cls, value: Any) -> List[str]:
        """تقسيم القوائم النصية مع إبقاء العناصر القصيرة وعدم إسقاطها."""
        text = cls._clean(value)
        if not text or text.strip() in {"/", "-"}:
            return []
        result: List[str] = []
        for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip().lstrip("•▪*-–— \t").strip()
            if line and line not in result and line not in {"/", "-"}:
                result.append(line)
        return result

    @classmethod
    def _first(cls, row: pd.Series, names: List[str], default: str = "") -> str:
        for name in names:
            if name in row.index:
                value = cls._clean(row.get(name))
                if value:
                    return value
        return default

    @classmethod
    def _paired_text(cls, row: pd.Series, arabic: str, french: str) -> Dict[str, str]:
        return {"ar": cls._clean(row.get(arabic, "")), "fr": cls._clean(row.get(french, ""))}

    def _from_excel(self, path: Path, sheet_name: Optional[str]) -> Dict[str, Any]:
        try:
            with pd.ExcelFile(path) as excel:
                chosen_sheet = sheet_name if sheet_name in excel.sheet_names else excel.sheet_names[0]
                df = pd.read_excel(excel, sheet_name=chosen_sheet)
        except Exception as exc:
            raise RNFCConnectorError(f"تعذر قراءة ملف Excel: {exc}") from exc

        df.columns = [str(c).strip() for c in df.columns]
        required = {"specialite_id", "codnom", "nom_spe_ar", "modQ_ar", "modc_ar"}
        missing_columns = sorted(required - set(df.columns))
        if missing_columns:
            raise RNFCConnectorError("أعمدة أساسية غير موجودة في ورقة RNFC: " + "، ".join(missing_columns))

        specialites: List[Dict[str, Any]] = []
        for row_index, row in df.iterrows():
            # modQ: عناصر تأهيلية/وحدات واردة في المرجع، وليست علاقات قبلية.
            modq_ar = self._lines(row.get("modQ_ar", ""))
            modq_fr = self._lines(row.get("modQ", ""))
            modc_ar = self._lines(row.get("modc_ar", ""))
            modc_fr = self._lines(row.get("modc", ""))
            cqp_ar = self._lines(row.get("listcqp_ar", ""))
            cqp_fr = self._lines(row.get("listcqp", ""))

            elements = []
            for i, (arabic_text, french_text) in enumerate(zip_longest_values(modq_ar, modq_fr), 1):
                elements.append({
                    "id": f"{self._first(row, ['specialite_id'], str(row_index + 1))}-MQ-{i:02d}",
                    "code": f"MQ-{i:02d}", "label": arabic_text or french_text, "label_ar": arabic_text,
                    "label_fr": french_text, "description": arabic_text or french_text,
                    "source_field": "modQ_ar + modQ" if modq_ar and modq_fr else ("modQ_ar" if modq_ar else "modQ"),
                    "source_status": "مستخرج من ملف RNFC؛ لا يتضمن الملف علاقة قبلية مصرحاً بها لهذا العنصر",
                    "prerequisites": [],
                })

            resources = [{"label": ar or fr, "label_ar": ar, "label_fr": fr,
                          "source_field": "modc_ar" if ar else "modc",
                          "source_status": "مستخرج حرفياً من ملف RNFC"}
                         for ar, fr in zip_longest_values(modc_ar, modc_fr)]
            cqp_items = [{"label": ar or fr, "label_ar": ar, "label_fr": fr,
                          "source_field": "listcqp_ar" if ar else "listcqp",
                          "source_status": "مستخرج حرفياً من ملف RNFC"}
                         for ar, fr in zip_longest_values(cqp_ar, cqp_fr)]

            spec_name = self._first(row, ["nom_spe_ar", "nom", "nom_fr"], "تخصص غير محدد")
            code = self._first(row, ["codnom", "code"])
            specialites.append({
                "id": self._first(row, ["specialite_id", "id"], str(row_index + 1)),
                "code": code,
                "label": self._first(row, ["nom", "nom_fr"], spec_name),
                "label_ar": spec_name,
                "label_fr": self._first(row, ["nom", "nom_fr"]),
                "type_formation": self._paired_text(row, "type_form_ar", "type_form"),
                "diplome": self._paired_text(row, "diplom_ar", "diplom"),
                "duree": self._paired_text(row, "duree_ar", "duree"),
                "niveau_scolaire": self._paired_text(row, "nivSC_ar", "nivSc"),
                "mode_formation": self._paired_text(row, "modFor_ar", "modFor"),
                "secteur": {"id": self._first(row, ["id_sect"]),
                            "label": self._first(row, ["nom_secteur_ar", "nom_secteur_fr"], "—"),
                            "label_fr": self._first(row, ["nom_secteur_fr"])},
                "domaine": {"id": self._first(row, ["id_dom"]),
                            "label": self._first(row, ["nom_domaine_ar", "nom_domaine_fr"], "—"),
                            "label_fr": self._first(row, ["nom_domaine_fr"])},
                "sous_domaine": {"id": self._first(row, ["id_sdom"]),
                                 "label": self._first(row, ["nom_sdomaine_ar", "nom_sdomaine_fr"], "—"),
                                 "label_fr": self._first(row, ["nom_sdomaine_fr"])},
                # توافق خلفي مع واجهة التطبيق الحالية: competences تعني عناصر modQ.
                "competences": elements,
                "elements_qualification": elements,
                "competences_professionnelles_cqp": cqp_items,
                "ressources_complementaires": resources,
                "objectifs_reference": self._lines(row.get("object_ar", row.get("object", ""))),
                "objectif_reference": self._paired_text(row, "object_ar", "object"),
                "definition_metier": self._paired_text(row, "def_ar", "def"),
                "appellations_metier": self._paired_text(row, "appel_ar", "appel"),
                "conditions_acces": self._paired_text(row, "exig_ar", "exig"),
                "evolution_reglementaire": self._paired_text(row, "evol_ar", "evol"),
                "modalites_evaluation": self._paired_text(row, "modeval_ar", "modeval"),
                "source_sheet": chosen_sheet,
                "source_row": int(row_index) + 2,
                "reference_warnings": [] if elements else ["لم يتم العثور على عناصر في modQ؛ لم تُنشأ عناصر افتراضية."],
            })

        return {
            "source": str(path), "sheet": chosen_sheet, "schema_version": "4.0",
            "stats": {
                "specialites": len(specialites),
                "elements_qualification": sum(len(s["elements_qualification"]) for s in specialites),
                "competences": sum(len(s["competences"]) for s in specialites),
                "competences_professionnelles_cqp": sum(len(s["competences_professionnelles_cqp"]) for s in specialites),
                "ressources_complementaires": sum(len(s["ressources_complementaires"]) for s in specialites),
            },
            "specialites": specialites,
        }

    def load_data(self, sheet_name: str = "المتوج بشهادة") -> Dict[str, Any]:
        path = self._find_rnfc_file()
        if not path:
            raise RNFCConnectorError(
                f"لم يتم العثور على ملف RNFC داخل: {self.data_dir}\n"
                "أنشئ مجلد data بجانب التطبيق وضع ملف Excel أو JSON داخله."
            )
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return self._from_excel(path, sheet_name)
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict) or not isinstance(payload.get("specialites"), list):
                raise ValueError("بنية JSON غير صالحة: يلزم مفتاح specialites من نوع list")
            payload.setdefault("source", str(path))
            payload.setdefault("schema_version", "4.0")
            payload.setdefault("stats", {
                "specialites": len(payload["specialites"]),
                "competences": sum(len(x.get("competences", [])) for x in payload["specialites"]),
            })
            return payload
        except Exception as exc:
            raise RNFCConnectorError(f"تعذر قراءة ملف JSON: {exc}") from exc


def zip_longest_values(left: List[str], right: List[str]):
    """إقران القائمتين حسب الموضع مع عدم إسقاط العناصر الزائدة من أي لغة."""
    count = max(len(left), len(right))
    return [(left[i] if i < len(left) else "", right[i] if i < len(right) else "")
            for i in range(count)]


def search_specialites(payload: Dict[str, Any], query: str = "") -> List[Dict[str, Any]]:
    items = payload.get("specialites", [])
    q = query.strip().casefold()
    if not q:
        return items
    return [item for item in items
            if q in " ".join(str(item.get(k, "")) for k in ("label", "label_ar", "label_fr", "code")).casefold()]
