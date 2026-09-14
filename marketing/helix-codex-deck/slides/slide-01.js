const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'cover',
  index: 1,
  title: 'Helix Codex'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.16, h: 5.625,
    fill: { color: theme.accent }
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 6.85, y: 1.30, w: 2.55, h: 0.82,
    fill: { color: theme.light, transparency: 88 },
    rectRadius: 0.16
  });
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 6.85, y: 2.28, w: 2.55, h: 0.82,
    fill: { color: theme.light, transparency: 88 },
    rectRadius: 0.16
  });
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 6.85, y: 3.26, w: 2.55, h: 0.82,
    fill: { color: theme.accent, transparency: 42 },
    rectRadius: 0.16
  });

  slide.addText("Helix Codex", {
    x: 0.72, y: 1.50, w: 5.9, h: 1.05,
    fontSize: 56, fontFace: HEAD, bold: true,
    color: "FFFFFF", align: "left", valign: "middle"
  });

  slide.addText("The operations OS your team can actually own.", {
    x: 0.72, y: 2.58, w: 5.9, h: 0.62,
    fontSize: 20, fontFace: BODY,
    color: theme.light, align: "left", valign: "middle"
  });

  slide.addText(
    "Chat, docs, tasks, calendar, on-call, attendance and an AI organization that executes — behind an audit trail, on your own hardware.",
    {
      x: 0.72, y: 3.42, w: 5.7, h: 1.0,
      fontSize: 13, fontFace: BODY,
      color: theme.secondary, align: "left", valign: "top", lineSpacingMultiple: 1.25
    }
  );

  slide.addText("Helix Codex OS   ·   Hatem Shalaby   ·   2026", {
    x: 0.72, y: 4.72, w: 6.0, h: 0.32,
    fontSize: 11, fontFace: BODY,
    color: theme.secondary, align: "left", valign: "middle"
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
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
