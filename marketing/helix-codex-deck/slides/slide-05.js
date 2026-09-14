const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'timeline',
  index: 5,
  title: 'A day in the app'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("A day in the app", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  slide.addShape(pres.shapes.LINE, {
    x: 0.9, y: 2.22, w: 8.1, h: 0,
    line: { color: theme.light, width: 2 }
  });

  const steps = [
    { n: "1", label: "Punch in", desc: "One tap. The server sets the time, not the phone." },
    { n: "2", label: "Catch up", desc: "Chat, mentions and notifications arrive in one stream." },
    { n: "3", label: "Get work done", desc: "Tasks move across the board and notify the next person." },
    { n: "4", label: "Read the SOP", desc: "The knowledge base holds the current version, not last year's." },
    { n: "5", label: "Close the day", desc: "Attendance totals itself and the manager sees the week." }
  ];

  steps.forEach((step, i) => {
    const cx = 1.4 + i * 1.75;

    slide.addShape(pres.shapes.OVAL, {
      x: cx - 0.35, y: 1.88, w: 0.7, h: 0.7,
      fill: { color: theme.accent }
    });
    slide.addText(step.n, {
      x: cx - 0.35, y: 1.88, w: 0.7, h: 0.7,
      fontSize: 20, fontFace: BODY, color: "FFFFFF", bold: true,
      align: "center", valign: "middle"
    });
    slide.addText(step.label, {
      x: cx - 0.8, y: 2.75, w: 1.6, h: 0.32,
      fontSize: 13, fontFace: HEAD, bold: true,
      color: theme.primary, align: "center", valign: "middle"
    });
    slide.addText(step.desc, {
      x: cx - 0.8, y: 3.08, w: 1.6, h: 1.0,
      fontSize: 10.5, fontFace: BODY,
      color: theme.secondary, align: "center", valign: "top",
      lineSpacingMultiple: 1.15
    });
  });

  slide.addText("Every one of those actions is recorded. The audit trail is not a separate system bolted on at the end.", {
    x: 0.6, y: 4.45, w: 8.8, h: 0.4,
    fontSize: 12, fontFace: BODY,
    color: theme.secondary, align: "left", valign: "middle"
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("05", {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, fontFace: BODY, color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = {
    primary: "2B2D42",
    secondary: "8D99AE",
    accent: "EF233C",
    light: "EDF2F4",
    bg: "FFFFFF"
  };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-05-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
