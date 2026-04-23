"""Curated allow-list of EHI tables to ingest into SQLite for v1.

Anything not listed here can still be reached at runtime via the generic
TSV-streaming `/api/tables/{name}` endpoint.
"""

# Tables that carry the most patient-facing clinical signal.
CURATED_TABLES: list[str] = [
    # Demographics
    "PATIENT",
    "PATIENT_2",
    "PATIENT_3",
    "PATIENT_4",
    "PATIENT_5",
    "PATIENT_6",
    "PAT_ADDR_CHNG_HX",
    "PAT_RACE",
    # Allergies
    "ALLERGY",
    "ALLERGY_REACTIONS",
    # Problems & history
    "PROBLEM_LIST",
    "PROBLEM_NOTES",
    "MEDICAL_HX",
    "SURGICAL_HX",
    "FAMILY_HX",
    "SOCIAL_HX",
    # Medications
    "ORDER_MED",
    "ORDER_MED_2",
    "ORDER_MED_3",
    "ORDER_MED_4",
    "ORDER_MEDINFO",
    "MEDICATION_NOTES",
    "RXFILL",
    "MAR_ADMIN_INFO",
    # Encounters
    "PAT_ENC",
    "PAT_ENC_2",
    "PAT_ENC_HSP",
    "PAT_ENC_DX",
    "PAT_ENC_RSN_VISIT",
    # Orders, labs, results
    "ORDER_PROC",
    "ORDER_PROC_2",
    "ORDER_RESULTS",
    "ORDER_RES_COMMENT",
    "ORDER_RES_COMP_CMT",
    # Imaging / radiology narrative (free-text impressions and full reports)
    "ORDER_IMPRESSION",
    "ORDER_NARRATIVE",
    "ORDER_RAD_READING",
    # Vitals / flowsheets
    "IP_FLWSHT_REC",
    "IP_FLWSHT_MEAS",
    "IP_FLOWSHEET_ROWS",
    "V_EHI_FLO_MEAS_VALUE",  # flowsheet measurement values (the numbers)
    # Notes
    "HNO_INFO",
    "HNO_PLAIN_TEXT",
    "NOTE_TEXT",
    # Immunizations / referrals
    "PAT_IMMUNIZATIONS",
    "REFERRAL",
    # MyChart messaging
    "MYC_MESG",
    "MYC_MESG_RCP",
    "MYC_MESG_RTF_TEXT",  # actual message body (RTF)
    # Health maintenance
    "HM_ACTIVE",
    "HM_HISTORICAL_STATUS",
]

# Columns to index per table (if present).
INDEX_COLUMNS = {
    "PAT_ID",
    "PAT_ENC_CSN_ID",
    "ORDER_PROC_ID",
    "ORDER_MED_ID",
    "NOTE_ID",
    "LINE",
    "PROBLEM_LIST_ID",
    "ALLERGY_ID",
    "CONTACT_DATE",
    "ORDERING_DATE",
    "RESULT_TIME",
    "START_DATE",
    "END_DATE",
}
