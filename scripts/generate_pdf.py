import re
import sys
from fpdf import FPDF


def sanitize(text):
    return (
        text.replace("\u2014", "--")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2026", "...")
        .replace("\u2192", "->")
        .replace("\u2190", "<-")
        .replace("\u2713", "v")
        .replace("\u2717", "x")
        .replace("\u2716", "x")
        .replace("\u00a0", " ")
        .replace("\u2022", "-")
        .replace("\u00b7", "-")
        .replace("\u2011", "-")
        .replace("\u2264", "<=")
        .replace("\u2265", ">=")
        .replace("\u00b1", "+/-")
        .replace("\u00d7", "x")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


SRC = sys.argv[1] if len(sys.argv) > 1 else "docs/PROJECT_ARCHITECTURE.md"
DST = sys.argv[2] if len(sys.argv) > 2 else "docs/PROJECT_ARCHITECTURE.pdf"
FONT_R = "E:\\Helix-Prime\\marketing\\assets\\fonts\\DejaVuSans.ttf"
FONT_B = "E:\\Helix-Prime\\marketing\\assets\\fonts\\DejaVuSans-Bold.ttf"
FONT_M = "E:\\Helix-Prime\\marketing\\assets\\fonts\\DejaVuSansMono.ttf"


class ArchPDF(FPDF):
    def __init__(self):
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 15, 18)
        self.add_font("DV", "", FONT_R)
        self.add_font("DV", "B", FONT_B)
        self.add_font("DM", "", FONT_M)
        self.add_page()
        self.set_font("DV", size=7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, sanitize("Helix Prime -- Project Architecture Document"), align="C")
        self.ln(3)
        self.cell(0, 5, sanitize("Generated 2026-09-21 | Commit 2c7ecd1 | 1743 tests passing"), align="C")
        self.ln(8)
        self.set_text_color(0, 0, 0)
        self.table_rows = []
        self.in_table = False

    def header(self):
        if self.page_no() > 1:
            self.set_y(8)
            self.set_font("DV", "", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 4, sanitize("Helix Prime -- Project Architecture"), align="L")
            self.cell(0, 4, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0, 0, 0)
            self.set_y(14)

    def write_table(self):
        if not self.table_rows:
            return
        num_cols = max(len(r) for r in self.table_rows)
        available = self.w - self.l_margin - self.r_margin
        base = available / num_cols
        for r in self.table_rows:
            while len(r) < num_cols:
                r.append("")
        col_widths = []
        for c in range(num_cols):
            max_w = 0
            for r in self.table_rows:
                clean = re.sub(r"\*\*|\*|`", "", r[c].strip())
                est = len(clean) * 1.6
                max_w = max(max_w, min(est, base * 2.5))
            col_widths.append(max(15, min(max_w, available - (num_cols - 1) * 2)))
        total = sum(col_widths)
        if total < available:
            col_widths[-1] += available - total

        row_h = 5
        is_header = True
        for row in self.table_rows:
            x_start = self.get_x()
            y_start = self.get_y()
            cell_texts = []
            for c, cell in enumerate(row):
                cell = cell.strip()
                bold = cell.startswith("**") and cell.endswith("**")
                if bold:
                    cell = cell[2:-2]
                italic = cell.startswith("*") and cell.endswith("*") and not cell.startswith("***")
                if italic:
                    cell = cell[1:-1]
                cell_texts.append((cell, bold, italic))
            max_lines = 1
            for cell, bold, italic in cell_texts:
                self.set_xy(x_start + sum(col_widths[:c]), y_start)
                if bold:
                    self.set_font("DV", "B", 7)
                elif italic:
                    self.set_font("DV", "", 7)
                else:
                    self.set_font("DV", "", 7)
                if is_header:
                    self.set_fill_color(40, 40, 50)
                    self.set_text_color(240, 240, 240)
                else:
                    self.set_fill_color(250, 250, 252)
                    self.set_text_color(30, 30, 30)
                lines = self.multi_cell(col_widths[c], row_h, sanitize(cell), border=0, dry_run=True, output="LINES")
                max_lines = max(max_lines, len(lines))
            actual_h = max_lines * row_h
            if self.get_y() + actual_h > self.h - 25:
                self.add_page()
                y_start = self.get_y()
            for c, (cell, bold, italic) in enumerate(cell_texts):
                self.set_xy(x_start + sum(col_widths[:c]), y_start)
                if bold:
                    self.set_font("DV", "B", 7)
                elif italic:
                    self.set_font("DV", "", 7)
                else:
                    self.set_font("DV", "", 7)
                if is_header:
                    self.set_fill_color(40, 40, 50)
                    self.set_text_color(240, 240, 240)
                else:
                    self.set_fill_color(250, 250, 252)
                    self.set_text_color(30, 30, 30)
                self.multi_cell(col_widths[c], row_h, sanitize(cell), border=1, fill=True)
            self.set_y(y_start + actual_h)
            self.set_text_color(0, 0, 0)
            is_header = False
        self.table_rows = []
        self.in_table = False
        self.ln(2)

    def render_inline(self, text, base_size=8):
        tokens = re.split(r"(\*\*.*?\*\*|\*.*?\*|`[^`]*`)", text)
        for tok in tokens:
            if not tok:
                continue
            tok = sanitize(tok)
            if tok.startswith("**") and tok.endswith("**"):
                self.set_font("DV", "B", base_size)
                self.write(base_size, tok[2:-2])
            elif tok.startswith("`") and tok.endswith("`"):
                self.set_font("DM", "", base_size - 1)
                self.write(base_size - 1, tok[1:-1])
                self.set_font("DV", "", base_size)
            elif tok.startswith("*") and tok.endswith("*") and not tok.startswith("***"):
                self.set_font("DV", "", base_size)
                self.write(base_size, tok[1:-1])
            else:
                self.set_font("DV", "", base_size)
                self.write(base_size, tok)


def generate(src, dst):
    pdf = ArchPDF()
    with open(src, "r", encoding="utf-8") as f:
        lines = f.readlines()

    code_block = False
    code_lang = ""

    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")

        if code_block:
            if line.strip().startswith("```"):
                code_block = False
                if pdf.get_y() > pdf.h - 40:
                    pdf.add_page()
                pdf.set_y(pdf.get_y() + 1)
                pdf.set_font("DV", "", 8)
                pdf.set_text_color(0, 0, 0)
            else:
                if pdf.get_y() > pdf.h - 25:
                    pdf.add_page()
                pdf.set_font("DM", "", 7)
                pdf.set_text_color(60, 60, 60)
                pdf.set_x(pdf.l_margin + 4)
                pdf.cell(0, 3.5, sanitize(line[:180]), new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
            continue

        if line.strip().startswith("```"):
            if pdf.get_y() > pdf.h - 30:
                pdf.add_page()
            code_lang = line.strip()[3:].strip()
            code_block = True
            pdf.set_font("DM", "", 8)
            pdf.set_text_color(80, 80, 120)
            pdf.cell(0, 5, f"  [{code_lang or 'code'} block]", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            continue

        if line.strip().startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip().split("|")[1:-1]]
            if all(re.match(r"^[-: ]+$", c) for c in cells):
                continue
            pdf.in_table = True
            pdf.table_rows.append(cells)
            continue
        elif pdf.in_table and (not line.strip().startswith("|")):
            pdf.write_table()

        if re.match(r"^#{1,6}\s", line):
            level = len(re.match(r"^(#+)", line).group(1))
            text = re.sub(r"^#{1,6}\s+", "", line)
            if pdf.get_y() > pdf.h - 40:
                pdf.add_page()
            pdf.ln(2 if level <= 2 else 1)
            sizes = {1: 14, 2: 12, 3: 10, 4: 9, 5: 8, 6: 7.5}
            bold = level <= 3
            pdf.set_font("DV", "B" if bold else "", sizes.get(level, 8))
            if level <= 2:
                pdf.set_text_color(25, 25, 60)
            elif level == 3:
                pdf.set_text_color(40, 40, 80)
            else:
                pdf.set_text_color(60, 60, 90)
            pdf.multi_cell(0, sizes.get(level, 8) * 0.45, sanitize(text), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            continue

        if line.strip() == "---":
            if pdf.get_y() > pdf.h - 20:
                pdf.add_page()
            pdf.set_draw_color(180, 180, 190)
            pdf.set_y(pdf.get_y() + 1)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(2)
            continue

        if re.match(r"^\s*[-*]\s", line) or re.match(r"^\s*\d+\.\s", line):
            indent = len(line) - len(line.lstrip())
            content = re.sub(r"^\s*[-*]\s|^\s*\d+\.\s", "", line).strip()
            if pdf.get_y() > pdf.h - 25:
                pdf.add_page()
            pdf.set_font("DV", "", 8)
            marker_w = 5
            pdf.set_x(pdf.l_margin + indent * 1.5 + 3)
            if not content[0].isdigit() if content else False:
                pdf.cell(marker_w, 4, "-")
            pdf.set_x(pdf.l_margin + indent * 1.5 + (6 if not (content and content[0].isdigit()) else 3))
            pdf.render_inline(sanitize(content), 8)
            pdf.ln(4)
            continue

        if re.match(r"^\s*>\s", line):
            content = re.sub(r"^\s*>\s?", "", line)
            if pdf.get_y() > pdf.h - 25:
                pdf.add_page()
            pdf.set_fill_color(240, 240, 245)
            pdf.set_x(pdf.l_margin + 2)
            pdf.set_font("DV", "", 8)
            pdf.set_text_color(80, 80, 100)
            pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 4, 4, sanitize(content), fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            continue

        if line.strip() == "":
            pdf.ln(1)
            continue

        if pdf.get_y() > pdf.h - 25:
            pdf.add_page()

        if pdf.in_table:
            pdf.write_table()

        pdf.set_font("DV", "", 8)
        pdf.set_x(pdf.l_margin)
        pdf.render_inline(sanitize(line.strip()), 8)
        pdf.ln(4)

    if pdf.in_table:
        pdf.write_table()

    pdf.output(dst)
    print(f"PDF generated: {dst}")


if __name__ == "__main__":
    generate(SRC, DST)
