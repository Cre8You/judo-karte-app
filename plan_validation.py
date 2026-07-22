import datetime
from typing import Optional, Tuple


def validate_plan_inputs(
    patient_id: str,
    disease_name: str,
    onset_date: datetime.date,
    rehab_start_date: datetime.date,
) -> Tuple[Optional[str], str]:
    """Validate required plan fields and return the patient ID for the prompt."""
    patient_id_for_prompt = patient_id or "未入力"

    if not disease_name:
        return "傷病名を入力してください", patient_id_for_prompt
    if rehab_start_date < onset_date:
        return "リハ開始日が発症日より前です。日付を確認してください", patient_id_for_prompt
    return None, patient_id_for_prompt
