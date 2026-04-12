import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

def generate_pdf(filename, data):
    doc = SimpleDocTemplate(filename, pagesize=letter)
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))

    doc.build([t])
    print(f"Generated {filename}")

if __name__ == "__main__":
    os.makedirs("tests/fixtures", exist_ok=True)
    
    # Treasury Dummy
    generate_pdf("tests/fixtures/real_invoice.pdf", [
        ['Date', 'Item', 'Amount', 'Tax', 'Approver'],
        ['2026-04-12', 'Software', '100000', '10000', 'Mickey'],
    ])
    
    # Grant Dummy
    generate_pdf("tests/fixtures/real_grant.pdf", [
        ['Date', 'Item', 'SubItem', 'Approved', 'Executed'],
        ['2026-05-01', 'Server', 'AWS', '500000', '150000'],
    ])
    
    # Payroll Dummy
    generate_pdf("tests/fixtures/real_payroll.pdf", [
        ['ID', 'Name', 'Base', 'Meal', 'Insurance', 'Tax'],
        ['E101', 'Donald', '5000000', '200000', '300000', '150000'],
    ])
    
    # Withholding Dummy
    generate_pdf("tests/fixtures/real_withholding.pdf", [
        ['Month', 'Type', 'Headcount', 'Total', 'Tax'],
        ['2026-06', 'Salary', '10', '25000000', '1200000'],
    ])
