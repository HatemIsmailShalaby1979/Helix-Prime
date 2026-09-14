const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'comparison',
  index: 15,
  title: "Why this wins where the giants don't"
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Why this wins where the giants don't", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, color: theme.primary, bold: true,
    align: "left", valign: "middle"
  });

  const leftRows = [
    { label: "Data location", value: "Someone else's cloud." },
    { label: "The AI's role", value: "Suggests. A person retypes it." },
    { label: "Cost shape", value: "Per seat, per module, forever." },
    { label: "Customisation", value: "Whatever the vendor roadmap allows." },
    { label: "On a phone", value: "A cut-down web view." }
  ];

  const rightRows = [
    { label: "Data location", value: "Your hardware, your rules." },
    { label: "The AI's role", value: "Executes inside a governance boundary." },
    { label: "Cost shape", value: "Self-host for nothing. Pay for live data." },
    { label: "Customisation", value: "Capability packs you add without touching core." },
    { label: "On a phone", value: "An installable app that works offline." }
  ];

  const cardY = 1.30;
  const cardH = 3.55;

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.60, y: cardY, w: 4.25, h: cardH,
    rectRadius: 0.16,
    fill: { color: theme.light },
    line: { color: theme.light, width: 0 }
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.15, y: cardY, w: 4.25, h: cardH,
    rectRadius: 0.16,
    fill: { color: theme.primary },
    line: { color: theme.primary, width: 0 }
  });

  slide.addText("The usual stack", {
    x: 0.88, y: 1.46, w: 3.7, h: 0.34,
    fontSize: 14, fontFace: HEAD, color: theme.secondary, bold: true,
    align: "left", valign: "middle"
  });

  slide.addText("Helix Codex", {
    x: 5.43, y: 1.46, w: 3.7, h: 0.34,
    fontSize: 14, fontFace: HEAD, color: "FFFFFF", bold: true,
    align: "left", valign: "middle"
  });

  for (let i = 0; i < 5; i++) {
    const rowY = 1.95 + i * 0.56;

    slide.addText(leftRows[i].label, {
      x: 0.88, y: rowY, w: 3.7, h: 0.22,
      fontSize: 10, fontFace: HEAD, color: theme.accent, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(leftRows[i].value, {
      x: 0.88, y: rowY + 0.22, w: 3.7, h: 0.32,
      fontSize: 11, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top"
    });

    slide.addText(rightRows[i].label, {
      x: 5.43, y: rowY, w: 3.7, h: 0.22,
      fontSize: 10, fontFace: HEAD, color: theme.accent, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(rightRows[i].value, {
      x: 5.43, y: rowY + 0.22, w: 3.7, h: 0.32,
      fontSize: 11, fontFace: BODY, color: "FFFFFF",
      align: "left", valign: "top"
    });
  }

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("15", {
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
  pres.writeFile({ fileName: "slide-15-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
