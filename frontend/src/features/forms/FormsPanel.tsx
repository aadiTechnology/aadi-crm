import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { FormRenderer } from '@/features/forms/FormRenderer'
import { EmptyState, LoadingSkeleton, StatusBadge } from '@/ui/chrome'
import {
  addFormField,
  ApiError,
  createForm,
  getForm,
  getFormVersion,
  getProject,
  listFormVersions,
  listForms,
  listProjects,
  previewForm,
  publishForm,
  removeFormField,
  reorderFormFields,
  replaceDraftFromPublished,
  updateForm,
  updateFormField,
  type FormDefinition,
  type FormField,
  type FormFieldInput,
  type FormFieldType,
  type FormPreview,
  type FormVersion,
  type Project,
} from '@/services/platform'

const FIELD_TYPES: { value: FormFieldType; label: string }[] = [
  { value: 'text', label: 'Text' },
  { value: 'long_text', label: 'Long text' },
  { value: 'number', label: 'Number' },
  { value: 'mobile', label: 'Mobile' },
  { value: 'email', label: 'Email' },
  { value: 'url', label: 'URL' },
  { value: 'date', label: 'Date' },
  { value: 'time', label: 'Time' },
  { value: 'dropdown', label: 'Dropdown' },
  { value: 'multi_select', label: 'Multi-select' },
  { value: 'radio', label: 'Radio' },
  { value: 'checkbox', label: 'Checkbox' },
  { value: 'currency', label: 'Currency' },
  { value: 'file', label: 'File' },
  { value: 'auto_number', label: 'Auto-number' },
]

const PICKLIST = new Set<FormFieldType>(['dropdown', 'multi_select', 'radio'])
const NO_DEFAULT = new Set<FormFieldType>(['multi_select', 'file', 'auto_number'])

const PALETTE: { title: string; hint?: string; types: FormFieldType[] }[] = [
  { title: 'Text', types: ['text', 'long_text'] },
  { title: 'Contact', types: ['mobile', 'email', 'url'] },
  { title: 'Value', types: ['number', 'currency', 'date', 'time'] },
  { title: 'Choice', types: ['dropdown', 'multi_select', 'radio', 'checkbox'] },
  {
    title: 'Definition only',
    hint: 'File and auto-number can be configured. They do not upload a file or generate a number.',
    types: ['file', 'auto_number'],
  },
]

type Draft = {
  field_key: string
  label: string
  field_type: FormFieldType
  required: boolean
  help_text: string
  section_name: string
  max_length: string
  min_value: string
  max_value: string
  options_text: string
  default_value: string
  currency_code: string
  max_size_mb: string
  extensions: string
  prefix: string
  pad_width: string
  checkbox_default: '' | 'true' | 'false'
}

type ProjectListState =
  | { status: 'loading' }
  | { status: 'ready'; items: Project[] }
  | { status: 'error'; message: string }

type FormListState =
  | { status: 'loading' }
  | { status: 'ready'; project: Project; items: FormDefinition[] }
  | { status: 'error'; message: string }

type DetailState =
  | { status: 'loading' }
  | { status: 'ready'; project: Project; form: FormDefinition }
  | { status: 'error'; message: string }

type VersionState =
  | { status: 'loading' }
  | { status: 'ready'; items: FormVersion[] }
  | { status: 'error'; message: string }

type PreviewState =
  | { status: 'loading' }
  | { status: 'ready'; project: Project; preview: FormPreview }
  | { status: 'error'; message: string }

type PublishedState =
  | { status: 'loading' }
  | { status: 'ready'; project: Project; version: FormVersion }
  | { status: 'error'; message: string }

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function typeLabel(fieldType: FormFieldType): string {
  return FIELD_TYPES.find((item) => item.value === fieldType)?.label ?? fieldType
}

function FieldPalette({
  selected,
  disabled,
  onPick,
}: {
  selected: FormFieldType
  disabled: boolean
  onPick: (fieldType: FormFieldType) => void
}) {
  return (
    <aside className="palette" aria-label="Field palette">
      <h3>Field palette</h3>
      <p className="muted">Choose a type, then set its properties.</p>
      {PALETTE.map((group) => (
        <div key={group.title} className="palette-group">
          <p className="palette-label">{group.title}</p>
          {group.hint ? <p className="muted">{group.hint}</p> : null}
          <div className="palette-items">
            {group.types.map((fieldType) => (
              <button
                key={fieldType}
                type="button"
                aria-pressed={!disabled && selected === fieldType}
                disabled={disabled}
                onClick={() => onPick(fieldType)}
              >
                {typeLabel(fieldType)}
              </button>
            ))}
          </div>
        </div>
      ))}
    </aside>
  )
}

function emptyDraft(): Draft {
  return {
    field_key: '',
    label: '',
    field_type: 'text',
    required: false,
    help_text: '',
    section_name: '',
    max_length: '',
    min_value: '',
    max_value: '',
    options_text: '',
    default_value: '',
    currency_code: 'INR',
    max_size_mb: '',
    extensions: '',
    prefix: '',
    pad_width: '4',
    checkbox_default: '',
  }
}

function draftFromField(field: FormField): Draft {
  return {
    field_key: field.field_key,
    label: field.label,
    field_type: field.field_type,
    required: field.required,
    help_text: field.help_text,
    section_name: field.section_name,
    max_length: field.max_length === undefined ? '' : String(field.max_length),
    min_value: field.min_value === undefined ? '' : String(field.min_value),
    max_value: field.max_value === undefined ? '' : String(field.max_value),
    options_text: (field.options ?? []).map((option) => `${option.value}|${option.label}`).join('\n'),
    default_value:
      field.field_type === 'checkbox' || field.default_value === undefined || field.default_value === null
        ? ''
        : String(field.default_value),
    currency_code: field.currency_code ?? 'INR',
    max_size_mb: field.max_size_mb === undefined ? '' : String(field.max_size_mb),
    extensions: (field.extensions ?? []).join(', '),
    prefix: field.prefix ?? '',
    pad_width: field.pad_width === undefined ? '4' : String(field.pad_width),
    checkbox_default: field.field_type === 'checkbox' && typeof field.default_value === 'boolean'
      ? field.default_value
        ? 'true'
        : 'false'
      : '',
  }
}

function optionalNumber(value: string, label: string): number | string | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) {
    return `${label} must be a number.`
  }
  return parsed
}

function buildFieldInput(draft: Draft, creating: boolean): FormFieldInput | string {
  const label = draft.label.trim()
  if (!label) {
    return 'Field label is required.'
  }
  const input: FormFieldInput = {
    label,
    field_type: draft.field_type,
    required: draft.required,
    help_text: draft.help_text.trim(),
    section_name: draft.section_name.trim(),
  }
  if (creating) {
    const key = draft.field_key.trim()
    if (!/^[a-z][a-z0-9_]{0,40}$/.test(key)) {
      return 'Field identifier must start with a letter and use lowercase letters, numbers, or underscores.'
    }
    input.field_key = key
  }
  if (draft.field_type === 'text' || draft.field_type === 'long_text') {
    const maxLength = optionalNumber(draft.max_length, 'Maximum length')
    if (typeof maxLength === 'string') {
      return maxLength
    }
    if (maxLength !== undefined) {
      input.max_length = maxLength
    }
  }
  if (draft.field_type === 'number' || draft.field_type === 'currency') {
    const minimum = optionalNumber(draft.min_value, 'Minimum')
    const maximum = optionalNumber(draft.max_value, 'Maximum')
    if (typeof minimum === 'string') {
      return minimum
    }
    if (typeof maximum === 'string') {
      return maximum
    }
    if (minimum !== undefined) {
      input.min_value = minimum
    }
    if (maximum !== undefined) {
      input.max_value = maximum
    }
  }
  if (draft.field_type === 'currency') {
    input.currency_code = draft.currency_code.trim() || 'INR'
  }
  if (PICKLIST.has(draft.field_type)) {
    const options = draft.options_text
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const separator = line.indexOf('|')
        if (separator <= 0 || separator === line.length - 1) {
          return null
        }
        return { value: line.slice(0, separator).trim(), label: line.slice(separator + 1).trim() }
      })
    if (options.length === 0 || options.some((option) => option === null)) {
      return 'Each option needs a value and a label, separated by |.'
    }
    input.options = options.filter((option): option is { value: string; label: string } => option !== null)
  }
  if (draft.field_type === 'file') {
    const size = optionalNumber(draft.max_size_mb, 'Maximum file size')
    if (typeof size === 'string') {
      return size
    }
    if (size !== undefined) {
      input.max_size_mb = size
    }
    const extensions = draft.extensions
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    if (extensions.length > 0) {
      input.extensions = extensions
    }
  }
  if (draft.field_type === 'auto_number') {
    input.prefix = draft.prefix.trim()
    const width = optionalNumber(draft.pad_width, 'Auto-number width')
    if (typeof width === 'string') {
      return width
    }
    if (width !== undefined) {
      input.pad_width = width
    }
  }
  if (!NO_DEFAULT.has(draft.field_type)) {
    if (draft.field_type === 'checkbox') {
      if (draft.checkbox_default === 'true') {
        input.default_value = true
      }
      if (draft.checkbox_default === 'false') {
        input.default_value = false
      }
    } else if (draft.default_value.trim()) {
      if (draft.field_type === 'number' || draft.field_type === 'currency') {
        const parsed = Number(draft.default_value.trim())
        if (!Number.isFinite(parsed)) {
          return 'Default value must be a number.'
        }
        input.default_value = parsed
      } else {
        input.default_value = draft.default_value.trim()
      }
    }
  }
  return input
}

function FieldEditor({
  draft,
  creating,
  submitting,
  error,
  onChange,
  onSubmit,
  onCancel,
}: {
  draft: Draft
  creating: boolean
  submitting: boolean
  error: string | null
  onChange: (draft: Draft) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onCancel?: () => void
}) {
  const showLength = draft.field_type === 'text' || draft.field_type === 'long_text'
  const showRange = draft.field_type === 'number' || draft.field_type === 'currency'
  return (
    <form className="stack field-form" onSubmit={onSubmit} noValidate>
      <h3>{creating ? 'Add field' : 'Edit field'}</h3>
      <label className="required-field">
        Field label
        <input value={draft.label} onChange={(event) => onChange({ ...draft, label: event.target.value })} />
      </label>
      {creating ? (
        <label className="required-field">
          Field identifier
          <input
            value={draft.field_key}
            onChange={(event) => onChange({ ...draft, field_key: event.target.value })}
          />
        </label>
      ) : (
        <p>
          Field identifier <strong>{draft.field_key}</strong>
        </p>
      )}
      {creating ? <p className="muted">The identifier cannot be changed after the field is saved.</p> : null}
      <label>
        Field type
        <select
          value={draft.field_type}
          onChange={(event) => onChange({ ...draft, field_type: event.target.value as FormFieldType })}
        >
          {FIELD_TYPES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Required</span>
        <input
          type="checkbox"
          checked={draft.required}
          onChange={(event) => onChange({ ...draft, required: event.target.checked })}
        />
      </label>
      <label>
        Section
        <input
          value={draft.section_name}
          onChange={(event) => onChange({ ...draft, section_name: event.target.value })}
        />
      </label>
      <label>
        Help text
        <input value={draft.help_text} onChange={(event) => onChange({ ...draft, help_text: event.target.value })} />
      </label>
      {showLength ? (
        <label>
          Maximum length
          <input
            value={draft.max_length}
            onChange={(event) => onChange({ ...draft, max_length: event.target.value })}
          />
        </label>
      ) : null}
      {showRange ? (
        <>
          <label>
            Minimum
            <input value={draft.min_value} onChange={(event) => onChange({ ...draft, min_value: event.target.value })} />
          </label>
          <label>
            Maximum
            <input value={draft.max_value} onChange={(event) => onChange({ ...draft, max_value: event.target.value })} />
          </label>
        </>
      ) : null}
      {draft.field_type === 'currency' ? (
        <label>
          Currency code
          <input
            value={draft.currency_code}
            onChange={(event) => onChange({ ...draft, currency_code: event.target.value })}
          />
        </label>
      ) : null}
      {PICKLIST.has(draft.field_type) ? (
        <>
          <label>
            Options
            <textarea
              aria-describedby="option-hint"
              value={draft.options_text}
              onChange={(event) => onChange({ ...draft, options_text: event.target.value })}
            />
          </label>
          <p className="muted" id="option-hint">
            One option per line, written as value|label.
          </p>
        </>
      ) : null}
      {draft.field_type === 'file' ? (
        <>
          <p className="muted">This stores the file field definition. Upload is not available.</p>
          <label>
            Maximum file size (MB)
            <input
              value={draft.max_size_mb}
              onChange={(event) => onChange({ ...draft, max_size_mb: event.target.value })}
            />
          </label>
          <label>
            Extensions
            <input
              value={draft.extensions}
              onChange={(event) => onChange({ ...draft, extensions: event.target.value })}
            />
          </label>
        </>
      ) : null}
      {draft.field_type === 'auto_number' ? (
        <>
          <p className="muted">This stores the auto-number definition. A number is not generated.</p>
          <label>
            Prefix
            <input value={draft.prefix} onChange={(event) => onChange({ ...draft, prefix: event.target.value })} />
          </label>
          <label>
            Width
            <input
              value={draft.pad_width}
              onChange={(event) => onChange({ ...draft, pad_width: event.target.value })}
            />
          </label>
        </>
      ) : null}
      {draft.field_type === 'checkbox' ? (
        <label>
          Default value
          <select
            value={draft.checkbox_default}
            onChange={(event) =>
              onChange({ ...draft, checkbox_default: event.target.value as Draft['checkbox_default'] })
            }
          >
            <option value="">No default</option>
            <option value="true">Checked</option>
            <option value="false">Unchecked</option>
          </select>
        </label>
      ) : null}
      {!NO_DEFAULT.has(draft.field_type) && draft.field_type !== 'checkbox' ? (
        <label>
          Default value
          <input
            value={draft.default_value}
            onChange={(event) => onChange({ ...draft, default_value: event.target.value })}
          />
        </label>
      ) : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      <div className="row-actions">
        <button type="submit" disabled={submitting}>
          {submitting ? 'Saving field' : creating ? 'Add field' : 'Save field'}
        </button>
        {onCancel ? (
          <button type="button" className="button-secondary" onClick={onCancel}>
            Cancel edit
          </button>
        ) : null}
      </div>
    </form>
  )
}

export function FormsPanel({ tenantId }: { tenantId: string }) {
  const { projectId, formId, versionId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const onNew = location.pathname.endsWith('/new')
  const previewing = location.pathname.endsWith('/preview')
  const [projects, setProjects] = useState<ProjectListState>({ status: 'loading' })
  const [forms, setForms] = useState<FormListState>({ status: 'loading' })
  const [detail, setDetail] = useState<DetailState>({ status: 'loading' })
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [draft, setDraft] = useState<Draft>(emptyDraft())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [versions, setVersions] = useState<VersionState>({ status: 'loading' })
  const [versionError, setVersionError] = useState<string | null>(null)
  const [publishReview, setPublishReview] = useState(false)
  const [preview, setPreview] = useState<PreviewState>({ status: 'loading' })
  const [published, setPublished] = useState<PublishedState>({ status: 'loading' })
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    setSubmitting(false)
    setFormError(null)
    setFieldError(null)
    setVersionError(null)
    setEditingId(null)
    setDraft(emptyDraft())
    setNotice(null)
  }, [location.pathname])

  useEffect(() => {
    if (projectId) {
      return
    }
    let cancelled = false
    setProjects({ status: 'loading' })
    listProjects(tenantId, { q: '', status: '' })
      .then((result) => {
        if (!cancelled) {
          setProjects({ status: 'ready', items: result.items })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setProjects({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, tenantId])

  useEffect(() => {
    if (!projectId || formId || onNew) {
      return
    }
    let cancelled = false
    setForms({ status: 'loading' })
    Promise.all([getProject(tenantId, projectId), listForms(tenantId, projectId)])
      .then(([project, listed]) => {
        if (!cancelled) {
          setForms({ status: 'ready', project, items: listed.items })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setForms({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [formId, onNew, projectId, tenantId])

  useEffect(() => {
    if (!projectId || !onNew) {
      return
    }
    let cancelled = false
    setDetail({ status: 'loading' })
    getProject(tenantId, projectId)
      .then((project) => {
        if (!cancelled) {
          setDetail({
            status: 'ready',
            project,
            form: {
              id: '',
              tenant_id: tenantId,
              project_id: projectId,
              name: '',
              description: '',
              status: 'draft',
              created_by: null,
              updated_by: null,
              created_at: '',
              updated_at: '',
              fields: [],
            },
          })
          setName('')
          setDescription('')
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [onNew, projectId, tenantId])

  useEffect(() => {
    if (!projectId || !formId || onNew || previewing || versionId) {
      return
    }
    let cancelled = false
    setDetail({ status: 'loading' })
    setVersions({ status: 'loading' })
    setPublishReview(false)
    Promise.all([
      getProject(tenantId, projectId),
      getForm(tenantId, projectId, formId),
      listFormVersions(tenantId, projectId, formId),
    ])
      .then(([project, form, listed]) => {
        if (!cancelled) {
          setDetail({ status: 'ready', project, form })
          setVersions({ status: 'ready', items: listed.items })
          setName(form.name)
          setDescription(form.description)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail({ status: 'error', message: messageFrom(error) })
          setVersions({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [formId, onNew, previewing, projectId, tenantId, versionId])

  useEffect(() => {
    if (!projectId || !formId || !previewing) {
      return
    }
    let cancelled = false
    setPreview({ status: 'loading' })
    Promise.all([getProject(tenantId, projectId), previewForm(tenantId, projectId, formId)])
      .then(([project, body]) => {
        if (!cancelled) {
          setPreview({ status: 'ready', project, preview: body })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setPreview({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [formId, previewing, projectId, tenantId])

  useEffect(() => {
    if (!projectId || !formId || !versionId) {
      return
    }
    let cancelled = false
    setPublished({ status: 'loading' })
    Promise.all([
      getProject(tenantId, projectId),
      getFormVersion(tenantId, projectId, formId, versionId),
    ])
      .then(([project, version]) => {
        if (!cancelled) {
          setPublished({ status: 'ready', project, version })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setPublished({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [formId, projectId, tenantId, versionId])

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!projectId) {
      return
    }
    const trimmed = name.trim()
    if (!trimmed) {
      setFormError('Form name is required.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      const created = await createForm(tenantId, projectId, { name: trimmed, description: description.trim() })
      navigate(`/tenants/${tenantId}/forms/${projectId}/${created.id}`)
    } catch (error) {
      setFormError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onSaveForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!projectId || !formId) {
      return
    }
    const trimmed = name.trim()
    if (!trimmed) {
      setFormError('Form name is required.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      const updated = await updateForm(tenantId, projectId, formId, {
        name: trimmed,
        description: description.trim(),
      })
      setDetail((current) => (current.status === 'ready' ? { ...current, form: updated } : current))
      setName(updated.name)
      setDescription(updated.description)
      setNotice('Form details saved.')
      setSubmitting(false)
    } catch (error) {
      setFormError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onSaveField(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (detail.status !== 'ready' || !projectId || !formId) {
      return
    }
    const built = buildFieldInput(draft, editingId === null)
    if (typeof built === 'string') {
      setFieldError(built)
      return
    }
    setSubmitting(true)
    setFieldError(null)
    try {
      const updated =
        editingId === null
          ? await addFormField(tenantId, projectId, formId, built)
          : await updateFormField(tenantId, projectId, formId, editingId, built)
      setDetail({ ...detail, form: updated })
      setDraft(emptyDraft())
      setEditingId(null)
      setNotice('Field saved.')
      setSubmitting(false)
    } catch (error) {
      setFieldError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onReorder(field: FormField, direction: -1 | 1) {
    if (detail.status !== 'ready' || !projectId || !formId) {
      return
    }
    const ids = detail.form.fields.map((item) => item.id)
    const index = ids.indexOf(field.id)
    const target = index + direction
    if (index < 0 || target < 0 || target >= ids.length) {
      return
    }
    const next = [...ids]
    const swap = next[target]
    if (!swap) {
      return
    }
    next[target] = field.id
    next[index] = swap
    setSubmitting(true)
    setFieldError(null)
    try {
      const updated = await reorderFormFields(tenantId, projectId, formId, next)
      setDetail({ ...detail, form: updated })
      setSubmitting(false)
    } catch (error) {
      setFieldError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function reloadDetail() {
    if (!projectId || !formId) {
      return
    }
    const [project, form, listed] = await Promise.all([
      getProject(tenantId, projectId),
      getForm(tenantId, projectId, formId),
      listFormVersions(tenantId, projectId, formId),
    ])
    setDetail({ status: 'ready', project, form })
    setVersions({ status: 'ready', items: listed.items })
    setName(form.name)
    setDescription(form.description)
  }

  async function onPublish() {
    if (!projectId || !formId) {
      return
    }
    setSubmitting(true)
    setVersionError(null)
    try {
      await publishForm(tenantId, projectId, formId)
      await reloadDetail()
      setPublishReview(false)
      setNotice('Version published.')
      setSubmitting(false)
    } catch (error) {
      setVersionError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onReplaceDraft() {
    if (!projectId || !formId) {
      return
    }
    setSubmitting(true)
    setVersionError(null)
    try {
      await replaceDraftFromPublished(tenantId, projectId, formId)
      await reloadDetail()
      setEditingId(null)
      setDraft(emptyDraft())
      setNotice('Draft replaced from the published version.')
      setSubmitting(false)
    } catch (error) {
      setVersionError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onRemove(field: FormField) {
    if (detail.status !== 'ready' || !projectId || !formId) {
      return
    }
    setSubmitting(true)
    setFieldError(null)
    try {
      const updated = await removeFormField(tenantId, projectId, formId, field.id)
      setDetail({ ...detail, form: updated })
      if (editingId === field.id) {
        setEditingId(null)
        setDraft(emptyDraft())
      }
      setNotice('Field removed.')
      setSubmitting(false)
    } catch (error) {
      setFieldError(messageFrom(error))
      setSubmitting(false)
    }
  }

  if (!projectId) {
    return (
      <section className="stack" aria-labelledby="forms-heading">
        <h2 id="forms-heading">Forms</h2>
        <p className="page-intro">Form definitions belong to one project.</p>
        {projects.status === 'loading' ? (
          <>
            <p role="status">Loading forms</p>
            <LoadingSkeleton />
          </>
        ) : null}
        {projects.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {projects.message}
          </p>
        ) : null}
        {projects.status === 'ready' && projects.items.length === 0 ? (
          <EmptyState title="No projects" message="No projects are available." />
        ) : null}
        {projects.status === 'ready' && projects.items.length > 0 ? (
          <ul className="project-list">
            {projects.items.map((project) => (
              <li key={project.id}>
                <Link to={`/tenants/${tenantId}/forms/${project.id}`}>{project.name}</Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  if (!formId && !onNew) {
    const canManage = forms.status === 'ready' && forms.project.access.can_manage_forms
    return (
      <section className="stack" aria-labelledby="form-list-heading">
        <Link to={`/tenants/${tenantId}/forms`}>Back to forms</Link>
        <h2 id="form-list-heading">
          {forms.status === 'ready' ? `${forms.project.name} forms` : 'Forms'}
        </h2>
        {forms.status === 'loading' ? <p role="status">Loading forms</p> : null}
        {forms.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {forms.message}
          </p>
        ) : null}
        {forms.status === 'ready' && forms.project.status === 'archived' ? (
          <p>This project is archived. A project manager can still change its form definitions.</p>
        ) : null}
        {canManage ? (
          <Link className="button-link" to={`/tenants/${tenantId}/forms/${projectId}/new`}>
            New form
          </Link>
        ) : null}
        {forms.status === 'ready' && forms.items.length === 0 ? (
          <EmptyState title="No forms" message="No form definitions yet." />
        ) : null}
        {forms.status === 'ready' && forms.items.length > 0 ? (
          <ul className="project-list">
            {forms.items.map((form) => (
              <li key={form.id}>
                <Link to={`/tenants/${tenantId}/forms/${projectId}/${form.id}`}>
                  <span>{form.name}</span>
                  <span className="muted">
                    {form.fields.length} fields
                    {form.current_published_version_number
                      ? ` · Version ${form.current_published_version_number}`
                      : ''}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  if (onNew) {
    const denied = detail.status === 'ready' && !detail.project.access.can_manage_forms
    return (
      <section className="stack" aria-labelledby="form-create-heading">
        <Link to={`/tenants/${tenantId}/forms/${projectId}`}>Back to forms</Link>
        <h2 id="form-create-heading">New form</h2>
        {detail.status === 'loading' ? <p role="status">Loading forms</p> : null}
        {detail.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {detail.message}
          </p>
        ) : null}
        {denied ? (
          <p role="alert" className="alert alert-error">
            You do not have permission to perform this action.
          </p>
        ) : null}
        {detail.status === 'ready' && !denied ? (
          <form className="panel stack" onSubmit={(event) => void onCreate(event)} noValidate>
            <label className="required-field">
              Form name
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label>
              Description
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            {formError ? (
              <p role="alert" className="alert alert-error">
                {formError}
              </p>
            ) : null}
            <button type="submit" disabled={submitting}>
              {submitting ? 'Creating form' : 'Create form'}
            </button>
          </form>
        ) : null}
      </section>
    )
  }

  if (previewing && projectId && formId) {
    return (
      <section className="stack" aria-labelledby="form-preview-heading">
        <Link to={`/tenants/${tenantId}/forms/${projectId}/${formId}`}>Back to form</Link>
        <h2 id="form-preview-heading">Preview</h2>
        {preview.status === 'loading' ? <p role="status">Loading preview</p> : null}
        {preview.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {preview.message}
          </p>
        ) : null}
        {preview.status === 'ready' ? (
          <FormRenderer
            name={preview.preview.name}
            description={preview.preview.description}
            fields={preview.preview.fields}
            mode="preview"
          />
        ) : null}
      </section>
    )
  }

  if (versionId && projectId && formId) {
    return (
      <section className="stack" aria-labelledby="form-render-heading">
        <Link to={`/tenants/${tenantId}/forms/${projectId}/${formId}`}>Back to form</Link>
        <h2 id="form-render-heading">Published form</h2>
        {published.status === 'loading' ? <p role="status">Loading published form</p> : null}
        {published.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {published.message}
          </p>
        ) : null}
        {published.status === 'ready' ? (
          <FormRenderer
            name={published.version.name}
            description={published.version.description}
            fields={published.version.fields}
            mode="published"
            versionNumber={published.version.version_number}
          />
        ) : null}
      </section>
    )
  }

  const canManage = detail.status === 'ready' && detail.project.access.can_manage_forms
  const fields = detail.status === 'ready' ? detail.form.fields : []
  const formDirty =
    detail.status === 'ready' && (name !== detail.form.name || description !== detail.form.description)
  let previousSection: string | null = null

  function selectField(field: FormField) {
    setEditingId(field.id)
    setDraft(draftFromField(field))
    setFieldError(null)
  }

  return (
    <section className="stack" aria-labelledby="form-detail-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/forms`}>Forms</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/tenants/${tenantId}/forms/${projectId}`}>
          {detail.status === 'ready' ? detail.project.name : 'Project'}
        </Link>
        <span aria-hidden="true">/</span>
        <span>{detail.status === 'ready' ? detail.form.name : 'Form'}</span>
      </nav>
      <div className="page-header">
        <div>
          <h2 id="form-detail-heading">{detail.status === 'ready' ? detail.form.name : 'Form'}</h2>
          <p className="page-intro">
            <Link to={`/tenants/${tenantId}/forms/${projectId}`}>Back to forms</Link>
          </p>
        </div>
      </div>
      {detail.status === 'loading' ? (
        <>
          <p role="status">Loading form</p>
          <LoadingSkeleton />
        </>
      ) : null}
      {detail.status === 'error' ? (
        <p role="alert" className="alert alert-error">
          {detail.message}
        </p>
      ) : null}
      {detail.status === 'ready' ? (
        <>
          <p>
            Status <StatusBadge tone="info">Draft</StatusBadge>
          </p>
          <p>
            {detail.form.current_published_version_number
              ? `Current published version ${detail.form.current_published_version_number}`
              : 'No published version yet.'}
          </p>
          {formDirty ? <p className="muted">Unsaved form details</p> : null}
          {notice ? (
            <p role="status" className="alert alert-ok">
              {notice}
            </p>
          ) : null}
          {canManage ? (
            <div className="row-actions">
              <Link className="button-link" to={`/tenants/${tenantId}/forms/${projectId}/${formId}/preview`}>
                Preview draft
              </Link>
              <button type="button" disabled={submitting} onClick={() => setPublishReview(true)}>
                Publish version
              </button>
              {detail.form.current_published_version_id ? (
                <button type="button" className="button-secondary" disabled={submitting} onClick={() => void onReplaceDraft()}>
                  Replace draft with published version
                </button>
              ) : null}
            </div>
          ) : null}
          {publishReview && canManage ? (
            <section className="panel stack" aria-labelledby="publish-review-heading">
              <h3 id="publish-review-heading">Review publication</h3>
              <p>
                Publishing creates an immutable version of this draft. The version number, fields, and validation stay
                as they are now. Later draft edits do not change a version that is already published.
              </p>
              <p>
                {detail.form.fields.length === 0
                  ? 'This draft has no fields.'
                  : `${detail.form.fields.length} field${detail.form.fields.length === 1 ? '' : 's'} will be copied into the new version.`}
              </p>
              <div className="row-actions">
                <button type="button" disabled={submitting} onClick={() => void onPublish()}>
                  {submitting ? 'Publishing' : 'Confirm publish'}
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  disabled={submitting}
                  onClick={() => setPublishReview(false)}
                >
                  Cancel publish
                </button>
              </div>
            </section>
          ) : null}
          {versionError ? (
            <p role="alert" className="alert alert-error">
              {versionError}
            </p>
          ) : null}
          <section className="panel stack">
            <h3>Published versions</h3>
            {versions.status === 'loading' ? (
              <>
                <p role="status">Loading versions</p>
                <LoadingSkeleton />
              </>
            ) : null}
            {versions.status === 'error' ? (
              <p role="alert" className="alert alert-error">
                {versions.message}
              </p>
            ) : null}
            {versions.status === 'ready' && versions.items.length === 0 ? <p>No versions have been published.</p> : null}
            {versions.status === 'ready' && versions.items.length > 0 ? (
              <ul className="project-list">
                {versions.items.map((version) => (
                  <li key={version.id}>
                    <Link to={`/tenants/${tenantId}/forms/${projectId}/${formId}/versions/${version.id}`}>
                      <span>Render version {version.version_number}</span>
                      <span className="muted">{version.current ? 'Current' : 'Published'}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
          {detail.project.status === 'archived' ? (
            <p>This project is archived. A project manager can still change its form definitions.</p>
          ) : null}
          {canManage ? (
            <form className="panel stack" onSubmit={(event) => void onSaveForm(event)} noValidate>
              <label className="required-field">
                Form name
                <input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label>
                Description
                <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
              </label>
              {formError ? (
                <p role="alert" className="alert alert-error">
                  {formError}
                </p>
              ) : null}
              <button type="submit" disabled={submitting}>
                {submitting ? 'Saving form' : 'Save form'}
              </button>
            </form>
          ) : (
            <p>{detail.form.description || 'No description.'}</p>
          )}
          <div className="builder">
            {canManage ? (
              <FieldPalette
                selected={draft.field_type}
                disabled={editingId !== null || submitting}
                onPick={(fieldType) => setDraft((current) => ({ ...current, field_type: fieldType }))}
              />
            ) : null}
            <div className="canvas">
              <h3>Form canvas</h3>
              {detail.form.description ? <p className="muted">{detail.form.description}</p> : null}
              {fields.length === 0 ? <EmptyState title="No fields" message="No fields yet." /> : null}
              {fields.length > 0 ? (
                <ol className="field-list">
                  {fields.map((field, index) => {
                    const section = field.section_name || 'General'
                    const showSection = section !== previousSection
                    previousSection = section
                    const selected = editingId === field.id
                    return (
                      <li
                        key={field.id}
                        className={[
                          selected ? 'is-selected' : '',
                          field.required ? 'is-required' : '',
                          selected && fieldError ? 'is-invalid' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        onClick={(event) => {
                          const target = event.target
                          if (!canManage || (target instanceof Element && target.closest('button'))) {
                            return
                          }
                          selectField(field)
                        }}
                      >
                        {showSection ? <p>Section {section}</p> : null}
                        <p>
                          <strong>{field.label}</strong> {field.required ? 'Required' : 'Optional'}
                        </p>
                        <p className="muted">
                          {field.field_key} · {typeLabel(field.field_type)}
                        </p>
                        {field.help_text ? <p>{field.help_text}</p> : null}
                        {field.options && field.options.length > 0 ? (
                          <p>{field.options.map((option) => option.label).join(', ')}</p>
                        ) : null}
                        {canManage ? (
                          <div className="row-actions">
                            <button
                              type="button"
                              className="button-secondary"
                              disabled={submitting || index === 0}
                              onClick={() => void onReorder(field, -1)}
                            >
                              Move {field.label} up
                            </button>
                            <button
                              type="button"
                              className="button-secondary"
                              disabled={submitting || index === fields.length - 1}
                              onClick={() => void onReorder(field, 1)}
                            >
                              Move {field.label} down
                            </button>
                            <button type="button" className="button-secondary" onClick={() => selectField(field)}>
                              Edit {field.label}
                            </button>
                            <button
                              type="button"
                              className="button-danger"
                              disabled={submitting}
                              onClick={() => void onRemove(field)}
                            >
                              Remove {field.label}
                            </button>
                          </div>
                        ) : null}
                      </li>
                    )
                  })}
                </ol>
              ) : null}
            </div>
            {canManage ? (
              <aside className={fieldError ? 'properties is-invalid' : 'properties'} aria-label="Field properties">
                <FieldEditor
                  draft={draft}
                  creating={editingId === null}
                  submitting={submitting}
                  error={fieldError}
                  onChange={setDraft}
                  onSubmit={(event) => void onSaveField(event)}
                  onCancel={
                    editingId
                      ? () => {
                          setEditingId(null)
                          setDraft(emptyDraft())
                          setFieldError(null)
                        }
                      : undefined
                  }
                />
              </aside>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  )
}
