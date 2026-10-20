import { useState, type FormEvent } from 'react'

import type { RenderField } from '@/services/platform'

export type FormValue = string | boolean | string[]

type Value = FormValue

const PICKLIST = new Set(['dropdown', 'multi_select', 'radio'])

function initialValue(field: RenderField): Value {
  if (field.field_type === 'checkbox') {
    return field.default_value === true
  }
  if (field.field_type === 'multi_select') {
    return []
  }
  if (field.default_value === undefined || field.default_value === null) {
    return ''
  }
  return String(field.default_value)
}

function textValue(value: Value | undefined): string {
  return typeof value === 'string' ? value : ''
}

function validate(fields: RenderField[], values: Record<string, Value>): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const field of fields) {
    if (field.field_type === 'auto_number') {
      continue
    }
    if (field.field_type === 'file') {
      if (field.required) {
        errors[field.field_key] = 'File upload is not available in this view.'
      }
      continue
    }
    const value = values[field.field_key]
    if (field.field_type === 'checkbox') {
      if (field.required && value !== true) {
        errors[field.field_key] = `${field.label} is required.`
      }
      continue
    }
    if (field.field_type === 'multi_select') {
      const selected = Array.isArray(value) ? value : []
      if (field.required && selected.length === 0) {
        errors[field.field_key] = `${field.label} is required.`
      }
      continue
    }
    const text = textValue(value).trim()
    if (field.required && !text) {
      errors[field.field_key] = `${field.label} is required.`
      continue
    }
    if (!text) {
      continue
    }
    if (field.field_type === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text)) {
      errors[field.field_key] = `${field.label} must be an email address.`
    }
    if (field.field_type === 'url' && !/^https?:\/\//.test(text)) {
      errors[field.field_key] = `${field.label} must start with http:// or https://.`
    }
    if (field.field_type === 'mobile' && !/^\+?[0-9]{8,15}$/.test(text)) {
      errors[field.field_key] = `${field.label} must contain 8 to 15 digits.`
    }
    if (field.field_type === 'number' || field.field_type === 'currency') {
      const parsed = Number(text)
      if (!Number.isFinite(parsed)) {
        errors[field.field_key] = `${field.label} must be a number.`
      } else if (field.min_value !== undefined && parsed < field.min_value) {
        errors[field.field_key] = `${field.label} is below the minimum.`
      } else if (field.max_value !== undefined && parsed > field.max_value) {
        errors[field.field_key] = `${field.label} is above the maximum.`
      }
    }
    if ((field.field_type === 'dropdown' || field.field_type === 'radio') && field.options) {
      if (!field.options.some((option) => option.value === text)) {
        errors[field.field_key] = `${field.label} must use one of the listed options.`
      }
    }
    if (typeof field.max_length === 'number' && text.length > field.max_length) {
      errors[field.field_key] = `${field.label} is too long.`
    }
  }
  return errors
}

function FieldControl({
  field,
  value,
  onChange,
}: {
  field: RenderField
  value: Value | undefined
  onChange: (value: Value) => void
}) {
  if (field.field_type === 'file') {
    return (
      <div>
        <p>
          <strong>{field.label}</strong> {field.required ? 'Required' : 'Optional'}
        </p>
        <p>File upload is not available in this view.</p>
        {field.extensions && field.extensions.length > 0 ? (
          <p>Allowed extensions: {field.extensions.join(', ')}</p>
        ) : null}
        {field.max_size_mb !== undefined ? <p>Maximum size: {field.max_size_mb} MB.</p> : null}
      </div>
    )
  }
  if (field.field_type === 'auto_number') {
    return (
      <div>
        <p>
          <strong>{field.label}</strong> {field.required ? 'Required' : 'Optional'}
        </p>
        <p>Auto-number is not generated in this view.</p>
        {field.prefix ? <p>Prefix {field.prefix}</p> : null}
        {field.pad_width !== undefined ? <p>Width {field.pad_width}</p> : null}
      </div>
    )
  }
  if (field.field_type === 'long_text') {
    return (
      <label>
        {field.label} {field.required ? 'Required' : 'Optional'}
        <textarea
          aria-required={field.required}
          value={textValue(value)}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    )
  }
  if (field.field_type === 'checkbox') {
    return (
      <label>
        <span>
          {field.label} {field.required ? 'Required' : 'Optional'}
        </span>
        <input
          type="checkbox"
          aria-required={field.required}
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
        />
      </label>
    )
  }
  if (field.field_type === 'dropdown') {
    return (
      <label>
        {field.label} {field.required ? 'Required' : 'Optional'}
        <select
          aria-required={field.required}
          value={textValue(value)}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose</option>
          {(field.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    )
  }
  if (field.field_type === 'radio' || field.field_type === 'multi_select') {
    const selected = Array.isArray(value) ? value : []
    return (
      <fieldset>
        <legend>
          {field.label} {field.required ? 'Required' : 'Optional'}
        </legend>
        {(field.options ?? []).map((option) => (
          <label key={option.value}>
            <span>{option.label}</span>
            <input
              type={field.field_type === 'radio' ? 'radio' : 'checkbox'}
              name={field.field_key}
              checked={field.field_type === 'radio' ? value === option.value : selected.includes(option.value)}
              onChange={() => {
                if (field.field_type === 'radio') {
                  onChange(option.value)
                  return
                }
                onChange(
                  selected.includes(option.value)
                    ? selected.filter((item) => item !== option.value)
                    : [...selected, option.value],
                )
              }}
            />
          </label>
        ))}
      </fieldset>
    )
  }
  const inputType =
    field.field_type === 'number' || field.field_type === 'currency'
      ? 'number'
      : field.field_type === 'date'
        ? 'date'
        : field.field_type === 'time'
          ? 'time'
          : field.field_type === 'email'
            ? 'email'
            : field.field_type === 'url'
              ? 'url'
              : 'text'
  return (
    <label>
      {field.label} {field.required ? 'Required' : 'Optional'}
      {field.field_type === 'currency' && field.currency_code ? ` (${field.currency_code})` : ''}
      <input
        type={inputType}
        aria-required={field.required}
        value={textValue(value)}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

export function FormRenderer({
  name,
  description,
  fields,
  mode,
  versionNumber,
  initialValues,
  externalErrors,
  submitting = false,
  onSave,
}: {
  name: string
  description: string
  fields: RenderField[]
  mode: 'preview' | 'published' | 'record'
  versionNumber?: number
  initialValues?: Record<string, Value>
  externalErrors?: Record<string, string>
  submitting?: boolean
  onSave?: (values: Record<string, Value>) => Promise<void> | void
}) {
  const [values, setValues] = useState<Record<string, Value>>(() =>
    Object.fromEntries(
      fields.map((field) => [field.field_key, initialValues?.[field.field_key] ?? initialValue(field)]),
    ),
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState<string | null>(null)
  let previousSection: string | null = null

  async function onCheck(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) {
      return
    }
    const next = validate(fields, values)
    setErrors(next)
    if (Object.keys(next).length > 0) {
      setNotice(null)
      return
    }
    if (mode === 'record' && onSave) {
      await onSave(values)
      return
    }
    setNotice(
      mode === 'preview'
        ? 'Preview checked these fields. No CRM record was saved.'
        : 'The published form checked these fields. No CRM record was saved.',
    )
  }

  return (
    <form className="stack form-render" onSubmit={(event) => void onCheck(event)} noValidate>
      <h3>{name}</h3>
      {mode === 'preview' ? (
        <p>Draft preview. Required fields are marked. Nothing is saved.</p>
      ) : mode === 'record' ? (
        <p>Published version {versionNumber}. Saving uses this version, not the current draft.</p>
      ) : (
        <p>Published version {versionNumber}. This schema stays as it was published.</p>
      )}
      {description ? <p>{description}</p> : null}
      {fields.length === 0 ? <p>This form has no fields to show.</p> : null}
      {fields.map((field) => {
        const section = field.section_name || 'General'
        const showSection = section !== previousSection
        previousSection = section
        return (
          <div key={field.field_key}>
            {showSection ? <p>Section {section}</p> : null}
            <FieldControl
              field={field}
              value={values[field.field_key]}
              onChange={(value) => {
                setValues((current) => ({ ...current, [field.field_key]: value }))
                setNotice(null)
              }}
            />
            {field.help_text ? <p>{field.help_text}</p> : null}
            {PICKLIST.has(field.field_type) && field.field_type === 'dropdown' && field.options ? (
              <p>{field.options.map((option) => option.label).join(', ')}</p>
            ) : null}
            {errors[field.field_key] || externalErrors?.[field.field_key] ? (
              <p role="alert" className="alert alert-error">
                {errors[field.field_key] || externalErrors?.[field.field_key]}
              </p>
            ) : null}
          </div>
        )
      })}
      {notice ? (
        <p role="status" className="alert alert-ok">
          {notice}
        </p>
      ) : null}
      {fields.length > 0 ? (
        <button type="submit" disabled={submitting}>
          {mode === 'record' ? (submitting ? 'Saving record' : 'Save record') : mode === 'preview' ? 'Check preview' : 'Check published form'}
        </button>
      ) : null}
    </form>
  )
}
