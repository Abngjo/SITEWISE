# SITEWISE API contract (frozen after 3 PM sync)

Base: same origin as the Space. Local: `http://localhost:7860`. Interactive docs: `/docs`.

| Method | Path | Returns | Used by |
|---|---|---|---|
| GET | `/api/health` | `{ok, project_id}` | deploy check |
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
| GET | `/api/ai/costs` | escalation rate, avg latency, est cost vs always-VLM | AI ops panel / efficiency slide |
| GET | `/api/report?lang=en|ar` | `{lang, direction, lines[], figures{}}` | report page |
| POST | `/api/admin/reset` | `{ok}` | reset before every rehearsal |
| GET | `/m` | mobile upload page (QR code target) | judges' phones |

Status colors: supported `#2ECC71`, uncertain `#F1C40F`, discrepancy `#E74C3C`, no_evidence `#9AA5AE`.
3D: load `/model.glb` once; node names are element_ids; recolor from `/api/model/status`.
