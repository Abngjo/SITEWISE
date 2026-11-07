# SITEWISE API contract (frozen after 3 PM sync)

Base: same origin as the Space. Local: `http://localhost:7860`. Interactive docs: `/docs`.

| Method | Path | Returns | Used by |
|---|---|---|---|
| GET | `/api/health` | `{ok, project_id, models:{warm, seconds|error}}` | deploy check, model warm-up status |
| GET | `/api/overview` | `{project, totals, certificate_no, baseline_handover, forecast_handover, handover_delay_days, counts{photos_this_certificate, possible_reuse, flags_awaiting_review, elements{supported,uncertain,discrepancy,no_evidence}}, ai{...}}` | dashboard landing page (one call) |
| GET | `/api/project` | project.json | header |
| GET | `/api/elements` | `Element[]` (with status, review, evidence_ids) | element list, 3D side panel |
| GET | `/api/model/status` | `{element_id: status}` | 3D viewer recolor |
| GET | `/api/boq` | BOQ rows | payments page |
| GET | `/api/evidence` | `Evidence[]` (current certificate) | evidence center |
| GET | `/api/evidence/{id}/image` | image file | thumbnails, side-by-side reuse view |
| POST | `/api/evidence` | `Evidence` | multipart: `file`, `element_id`, `capture_time?`, `time_source?`, `uploader?` |
| POST | `/api/elements/{id}/review` | `{element, model_status, audit, schedule}` | THE demo moment: one call returns everything to refresh |
| GET | `/api/payments/audit` | `{certificate_no, items[], totals{}}` | payment audit page |
| GET | `/api/schedule/forecast?delay_task=T-130&delay_days=5` | forecast with `handover_delay_days`, `critical_path`, `tasks[]` | schedule page + what-if |
| GET | `/api/safety` | `Flag[]` | safety page |
| GET | `/api/ai/costs` | escalation rate, avg latency, est cost vs always-VLM, cache_hits | AI ops panel / efficiency slide |
| GET | `/api/report?lang=en|ar` | `{lang, direction, lines[], figures{}}` | report page |
| GET | `/api/audit-letter?lang=en|ar` | `{lang, direction, header[], opening, opening_source, summary, items[], closing, findings[], figures{}}` | draft letter to contractor (figures from code; LLM writes only the opening, no digits allowed) |
| GET | `/api/bim/summary` | `{schema, project, storeys[], element_counts{IfcClass:n}, total_elements, mapped_elements, unmapped_ifc_elements[], sitewise_records_missing_in_ifc[]}` | BIM page header: parsed live from project.ifc |
| GET | `/api/bim/elements` | `[{ifc_guid, ifc_class, name, element_id, storey, mapped, boq_item_id, task_id, guid_matches_record}]` | BIM to BOQ to schedule mapping table |
| GET | `/api/bim/elements/{element_id}` | one row + `status` + `record` | 3D click panel: show IFC GUID / class / storey |
| POST | `/api/bim/import` | summary + `elements_preview[]` (multipart `file`=.ifc) | "Import BIM" demo step |
| GET | `/api/model/claim-view` | `{element_id: claimed|certified|not_claimed}` | 3D "Contractor's claim" toggle |
| GET | `/api/model/timeline` | `[{key, label, date, caption, status{element_id: status}}]` | 3D certificate replay |
| GET | `/api/bim/export` | IFC file with Pset `SITEWISE_Evidence` on every element | "Export as-verified IFC" |
| POST | `/api/ask` | `{answer, grounded: true|false|null, model, blocked_figures?}` (JSON `{question, lang}`) | Ask SITEWISE; every figure verified against computed data |
| POST | `/api/admin/reset` | `{ok}` | reset before every rehearsal |
| GET | `/m` | mobile upload page (QR code target) | judges' phones |

Status colors: supported `#2ECC71`, uncertain `#F1C40F`, discrepancy `#E74C3C`, no_evidence `#9AA5AE`.
3D: load `/model.glb` once; node names are element_ids; recolor from `/api/model/status`.

Notes: `Evidence` responses never include the `embedding` field. If AI fails, `ai.error` is set and `ai.requires_review` is true (no 500).

AIResult additions: `claimed_complete` (bool: element claimed in current certificate → VLM always judges completion), `escalation_reason` (completion_check | label_mismatch | low_confidence | null), `completion` (complete | partial | not_started | unclear | null), `completion_pct` (100 | 50 | 0 | null: set by code from `completion`, display only, never feeds payment), `phase` (string | null, from `PHASES` in `ai/inference.py`), `authenticity` (looks_real | possibly_edited | possibly_ai_generated | unclear | null). `vlm` also carries `phase`, `authenticity`, `authenticity_reason`.

Evidence additions: `photo_meta` `{file_taken_at, camera, software, has_camera_metadata, ai_marker, location{lat, lon, source: photo_gps|device_at_upload, accuracy_m, distance_from_site_km}|null}`. POST `/api/evidence` also takes optional `gps_lat`, `gps_lon`, `gps_accuracy_m`. New `Flag.type` values, all review-only, on `Evidence.flags` but not in `/api/safety`: `no_camera_metadata`, `photo_predates_period`, `photo_date_in_future`, `capture_time_mismatch`, `off_site`, `authenticity_review`. `/api/project` adds `site_location` `{lat, lon, radius_km, note}`.

Schedule forecast additions: `delay_exposure_qar`, `delay_damages_per_day_qar`, `delay_damages_note`. Overview adds `delay_exposure_qar`.
