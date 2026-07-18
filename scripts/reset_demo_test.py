#!/usr/bin/env python3
"""Reset the manual sort-testing directory to a pristine state.

`demo_sort_test/` is git-ignored local scratch used to try OCR File Sorter by
hand. A "Move" sort empties its inbox, so run this to regenerate the full set of
sample PDFs:

    python scripts/reset_demo_test.py

Requires PyMuPDF (already a project dependency). This script is the source of
truth for the fixture; running it always yields the same pristine layout.
"""
import os
import shutil

import fitz  # PyMuPDF

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(REPO_ROOT, "demo_sort_test")
INBOX = os.path.join(DEMO_DIR, "inbox")

# filename (under inbox/) -> embedded text. None = no text layer (a blank scan).
# Each text contains exactly one keyword from src/mappings/example.json so the
# preview routes it to the destination documented in README.txt.
DEMO_FILES = {
    "2024-03_invoice_acme.pdf":
        "INVOICE\n\nAcme Corp\nInvoice #2024-03\nDate: 2024-03-15\nAmount due: $1,240.00",
    "2024-04_invoice_globex.pdf":
        "INVOICE\n\nGlobex Inc\nInvoice #2024-04\nDate: 2024-04-02\nAmount due: $860.00",
    "statement_of_account_march.pdf":
        "Statement of Account\n\nMarch 2024\nOpening balance: $500.00\nClosing balance: $1,120.00",
    "purchase_order_5567.pdf":
        "Purchase Order\n\nPO Number: 5567\nVendor: Initech\nItems: 3 widgets",
    "payroll_summary_q1.pdf":
        "Payroll Summary\n\nQ1 2024\nGross pay: $45,000\nNet pay: $33,750",
    "coffee_receipt.pdf":
        "Receipt\n\nThe Daily Grind Cafe\n1x Latte    $4.50\nThank you!",
    "final_report_project_x.pdf":
        "Final Report\n\nProject X\nStatus: complete\nOutcome: delivered on time",
    "job_application_form.pdf":
        "Application Form\n\nPosition: Software Engineer\nName: ______\nExperience: ______",
    "confidential_memo.pdf":
        "CONFIDENTIAL\n\nInternal memo\nDistribution: management only\nSubject: reorganisation",
    "meeting_notes.pdf":
        "Meeting Notes\n\nWeekly team sync\nAttendees: Alex, Sam, Jo\n"
        "Action items: follow up on design tickets; schedule next sync Thursday.",
    "blank_scan.pdf": None,  # no text layer -> "unreadable" in the preview
}

# Lives in inbox/subfolder/ so it only appears when "Deep Audit" is enabled.
NESTED_FILE = (
    os.path.join("subfolder", "nested_invoice_2024.pdf"),
    "INVOICE\n\nNested Vendor Ltd\nInvoice #N-2024\nAmount due: $99.00",
)

README = """DEMO SORT TEST
==============

A set of sample PDFs to try OCR File Sorter (v2.0+).

Regenerate this folder any time with:  python scripts/reset_demo_test.py

HOW TO USE
1. Launch OCR File Sorter.
2. Mapping: choose  example.json
3. Output Folder: click "Choose..." and pick any empty folder for the results.
4. Click "Add Folder..." and pick this folder's  inbox  subfolder
   (path ends in \\demo_sort_test\\inbox).
5. Click "Sort Files". A PREVIEW appears listing what each PDF will do.
6. Choose "Move" or "Copy" (or Cancel).
   - Move  -> files leave inbox and go under your Output Folder.
   - Copy  -> originals stay in inbox; copies go to the Output Folder.
7. Click "Undo Last Sort" to put everything back (works even after reopening).

WHAT TO EXPECT IN THE PREVIEW
  2024-03_invoice_acme.pdf ....... 2024 Invoices
  2024-04_invoice_globex.pdf ..... 2024 Invoices
  statement_of_account_march.pdf . Statements
  purchase_order_5567.pdf ........ Purchase Orders
  payroll_summary_q1.pdf ......... Payroll
  coffee_receipt.pdf ............. Receipts
  final_report_project_x.pdf ..... Reports
  job_application_form.pdf ....... Applications
  confidential_memo.pdf .......... Confidential
  meeting_notes.pdf .............. no match (stays put)
  blank_scan.pdf ................. unreadable (no text layer)
  subfolder\\nested_invoice_2024.pdf  ... only appears with "Deep Audit"

Sorted files land under your chosen Output Folder, in a subfolder per
destination. "Open the destination folder?" after sorting takes you there.

Tip: "Deep Audit" (include the subfolder) and "Scan first page only" now live in
File > Preferences. Untick "Scan first page only" if you add multi-page PDFs
whose keyword isn't on page 1.
"""


def make_pdf(path, text):
    """Write a one-page PDF containing `text`, or a blank page if text is None."""
    doc = fitz.open()
    page = doc.new_page()
    if text:
        rect = fitz.Rect(72, 72, page.rect.width - 72, page.rect.height - 72)
        page.insert_textbox(rect, text, fontsize=12)
    doc.save(path)
    doc.close()


def main():
    # Rebuild the inbox from scratch (leaves demo_sort_test/ itself in place).
    if os.path.isdir(INBOX):
        shutil.rmtree(INBOX)
    os.makedirs(os.path.join(INBOX, "subfolder"))

    for name, text in DEMO_FILES.items():
        make_pdf(os.path.join(INBOX, name), text)
    nested_rel, nested_text = NESTED_FILE
    make_pdf(os.path.join(INBOX, nested_rel), nested_text)

    os.makedirs(DEMO_DIR, exist_ok=True)
    with open(os.path.join(DEMO_DIR, "README.txt"), "w", encoding="utf-8") as f:
        f.write(README)

    print(f"Reset {INBOX}")
    print(f"  {len(DEMO_FILES)} PDFs in inbox + 1 in subfolder/ (deep-audit only)")
    print("Ready to sort with mapping 'example.json'.")


if __name__ == "__main__":
    main()
