const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'process',
  index: 7,
  title: 'Operations that run on a rail'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Operations that run on a rail", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  const steps = [
    { label: "Submit", desc: "A manager raises the request." },
    { label: "Gate", desc: "The governance gate checks it." },
    { label: "Approve", desc: "An approver decides, and the reason is recorded." },
    { label: "Execute", desc: "The engine runs the work." },
    { label: "Audit", desc: "The action lands in the trail with its correlation id." }
  ];

  const xs = [0.60, 2.42, 4.24, 6.06, 7.88];

  steps.forEach((step, i) => {
    const x = xs[i];

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: 1.45, w: 1.5, h: 0.85,
      fill: { color: theme.primary },
      rectRadius: 0.16
    });
    slide.addText(step.label, {
      x: x + 0.08, y: 1.67, w: 1.34, h: 0.4,
      fontSize: 13, fontFace: HEAD, bold: true,
      color: "FFFFFF", align: "center", valign: "middle"
    });
    slide.addText(step.desc, {
      x: x, y: 2.42, w: 1.5, h: 0.75,
      fontSize: 10, fontFace: BODY,
      color: theme.secondary, align: "center", valign: "top",
      lineSpacingMultiple: 1.15
    });
  });

  const lines = [
    "Every mutating action goes through the engine and a gate.",
    "Nothing executes without the approval it requires.",
    "Every step keeps its correlation id, so any action can be traced end to end."
  ];
  const lineYs = [3.45, 3.95, 4.45];

  lines.forEach((line, i) => {
    const y = lineYs[i];

    slide.addShape(pres.shapes.OVAL, {
      x: 0.62, y: y + 0.11, w: 0.18, h: 0.18,
      fill: { color: theme.accent }
    });
    slide.addText(line, {
      x: 1.0, y: y, w: 8.3, h: 0.4,
      fontSize: 12.5, fontFace: BODY,
      color: theme.primary, align: "left", valign: "middle"
    });
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("07", {
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
  pres.writeFile({ fileName: "slide-07-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
