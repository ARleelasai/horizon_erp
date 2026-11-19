"""One way to tell people something: desk bell notification + email.

The bell notification (Notification Log) always works. Email is queued only
when the site has a default outgoing Email Account; without one Frappe raises
OutgoingEmailError, which is caught and logged so a missing mail server never
breaks a business transaction or a scheduler run.
"""

import frappe
from frappe.utils import strip_html


def notify(recipients, subject, message, reference_doctype=None, reference_name=None, attachments=None):
	recipients = [r for r in (recipients or []) if r and r not in ("Administrator", "Guest")]
	if not recipients:
		return
	for user in recipients:
		if not frappe.db.exists("User", user):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": message,
				"document_type": reference_doctype,
				"document_name": reference_name,
				"from_user": frappe.session.user if frappe.session.user != "Guest" else "Administrator",
			}
		).insert(ignore_permissions=True)
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			attachments=attachments,
		)
	except frappe.OutgoingEmailError:
		frappe.logger("horizon").warning(f"email not queued (no outgoing account): {subject} -> {recipients}: {strip_html(message)[:200]}")
