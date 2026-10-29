# Support ownership — original roadmap Sprint 12

Date: 21 October 2026. No person was named in the repository as the owner of deployment, the database, backup, restore, monitoring, or application support. This table does not invent those names. Escalation contacts were not supplied.

| Role | Responsibility | Primary owner | Backup owner | Escalation path |
|---|---|---|---|---|
| Product owner | Accept Sprint 11, accept or reject release, confirm backup policy and UAT | **Owner decision required** | **Owner decision required** | Not supplied |
| Tenant Admin | Tenant profile, users, and tenant settings, as described in the PRD | **Owner decision required** | **Owner decision required** | Not supplied |
| Project manager | Project membership, forms, records, imports, and project reports for one project | **Owner decision required** | **Owner decision required** | Not supplied |
| Deployment | Decide the target host and authorize a deploy | **Owner decision required** | **Owner decision required** | Not supplied |
| Database | Choose `CRM_DATABASE_PATH`, apply migrations to a copy, protect the SQLite file | **Owner decision required** | **Owner decision required** | Not supplied |
| Backup | Run the approved backup | **Owner decision required** | **Owner decision required** | Not supplied |
| Restore | Restore only after approval, into an isolated file | **Owner decision required** | **Owner decision required** | Product owner, not named |
| Monitoring | Watch `aadi_crm` logs and any future alert route | **Owner decision required** | **Owner decision required** | Not supplied |
| Application support | Triage CRM 4xx/5xx, import jobs, and reminder states | **Owner decision required** | **Owner decision required** | Not supplied |
| Control Plane | Sessions, `audit.read`, and platform availability | **Owner decision required.** This sprint did not change that repository | **Owner decision required** | Not supplied |

The CRM code roles used by authorization are `project_manager` and `project_member`. The PRD also names Platform Super Admin, Tenant Admin, and Project Manager. No login for a separate human pass of each role was identified.
