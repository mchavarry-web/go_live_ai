module Admin::AdminHelper
  # Format a string timestamp coming from FastAPI (ISO-ish). Returns "—"
  # when the value is blank or unparseable, which keeps the view free of
  # ad-hoc rescue modifiers.
  def fmt_iso_time(value, format = "%Y-%m-%d %H:%M")
    return "—" if value.blank?
    Time.parse(value.to_s).strftime(format)
  rescue ArgumentError
    "—"
  end
end
