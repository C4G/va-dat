# Written using the assist of ChatGPT

import sys
import os
from bs4 import BeautifulSoup


# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================

def css_path(el):
    path = []
    while el and el.name:
        sibling_index = 1
        sibling = el
        while sibling.previous_sibling:
            sibling = sibling.previous_sibling
            if getattr(sibling, "name", None) == el.name:
                sibling_index += 1

        if sibling_index > 1:
            path.append(f"{el.name}:nth-of-type({sibling_index})")
        else:
            path.append(el.name)

        el = el.parent

    return " > ".join(reversed(path))


def element_location(element):
    if element is None:
        return None

    attrs = dict(element.attrs)

    return {
        "tag": element.name,
        "id": attrs.get("id"),
        "class": attrs.get("class"),
        "css_path": css_path(element),
        "attributes": attrs,
        "text_preview": element.get_text(strip=True)[:80]
    }


def issue(rule_id, rule_name, element, description):
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "location": element_location(element),
        "description": description
    }


# ==========================================================
# MAIN AUDIT FUNCTION
# ==========================================================

def audit_forms(file_path):

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    results = []

    # ==========================================================
    # FORM CONTROLS (FILTERED TO INTERACTIVE CONTROLS ONLY)
    # ==========================================================

    form_controls = []

    for control in soup.find_all(["input", "select", "textarea"]):

        # Skip non-interactive input types
        if control.name == "input":
            input_type = (control.get("type") or "text").lower()

            if input_type in [
                "hidden",
                "submit",
                "reset",
                "button",
                "image"
            ]:
                continue

        form_controls.append(control)

    # ==========================================================
    # INPUT LABEL ASSOCIATION
    # ==========================================================

    for control in form_controls:

        control_id = control.get("id")
        has_label = False

        # <label for="id">
        if control_id:
            if soup.find("label", attrs={"for": control_id}):
                has_label = True

        # Wrapped by <label>
        if control.find_parent("label"):
            has_label = True

        # aria-label
        if control.get("aria-label"):
            has_label = True

        # aria-labelledby
        if control.get("aria-labelledby"):
            has_label = True

        # FORM_LABEL_001 — Missing label
        if not has_label:
            results.append(issue(
                "FORM_LABEL_001",
                "Form control missing programmatic label",
                control,
                "Form control does not have an associated label."
            ))

        # FORM_LABEL_003 — Placeholder used as only label
        if control.get("placeholder") and not has_label:
            results.append(issue(
                "FORM_LABEL_003",
                "Placeholder used as only label",
                control,
                "Placeholder text is used without a programmatically associated label."
            ))

    # ==========================================================
    # FIELDSET / LEGEND
    # ==========================================================

    for fieldset in soup.find_all("fieldset"):

        legend = fieldset.find("legend")

        # FORM_GROUP_001 — Fieldset missing legend
        if not legend:
            results.append(issue(
                "FORM_GROUP_001",
                "Fieldset missing legend",
                fieldset,
                "Fieldset does not contain a legend element."
            ))

    # ==========================================================
    # REQUIRED FIELDS
    # ==========================================================

    for control in form_controls:

        # Already programmatically required
        if "required" in control.attrs:
            continue

        control_id = control.get("id")

        # Heuristic: label contains *
        if control_id:
            label = soup.find("label", attrs={"for": control_id})
            if label and "*" in label.get_text():
                results.append(issue(
                    "FORM_REQUIRED_001",
                    "Required field not programmatically designated",
                    control,
                    "Field appears visually required but lacks 'required' attribute."
                ))

    # ==========================================================
    # ARIA-DESCRIBEDBY VALIDATION
    # ==========================================================

    for control in form_controls:

        describedby = control.get("aria-describedby")
        if describedby:
            ids = describedby.split()
            for ref_id in ids:
                if not soup.find(id=ref_id):
                    results.append(issue(
                        "FORM_INSTR_001",
                        "aria-describedby reference not found",
                        control,
                        f"aria-describedby references missing ID '{ref_id}'."
                    ))

    # ==========================================================
    # ERROR MESSAGE ASSOCIATION
    # ==========================================================

    for control in form_controls:

        if control.get("aria-invalid") == "true":
            describedby = control.get("aria-describedby")

            if not describedby:
                results.append(issue(
                    "FORM_ERROR_001",
                    "Error message not programmatically associated",
                    control,
                    "Invalid form control lacks aria-describedby linking to error message."
                ))

    # ==========================================================
    # CUSTOM INTERACTIVE CONTROLS
    # ==========================================================

    for el in soup.find_all(True):

        if el.get("onclick") and el.name not in ["button", "a", "input"]:
            if not el.get("role"):
                results.append(issue(
                    "FORM_CUSTOM_001",
                    "Custom interactive element missing role",
                    el,
                    "Element has click handler but no semantic role."
                ))

    return results


# ==========================================================
# CLI ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python audit_forms.py <file.html>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    results = audit_forms(file_path)

    print("\n=== FORM ACCESSIBILITY AUDIT RESULTS ===\n")

    if not results:
        print("No issues found.")
        sys.exit(0)

    for r in results:
        print(f"[{r['rule_id']}] {r['rule_name']}")

        location = r.get("location")

        if location:
            if location.get("css_path"):
                print(f"  Location: {location['css_path']}")
            if location.get("id"):
                print(f"  ID: {location['id']}")
            if location.get("attributes"):
                print(f"  Attributes: {location['attributes']}")
            if location.get("text_preview"):
                print(f"  Text Preview: \"{location['text_preview']}\"")

        print(f"  Description: {r['description']}")
        print()

    sys.exit(2)