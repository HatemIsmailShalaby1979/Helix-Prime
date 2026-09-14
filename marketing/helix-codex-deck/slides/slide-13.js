const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'grid',
  index: 13,
  title: 'Grows with the business, not against it'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Grows with the business, not against it", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, color: theme.primary, bold: true,
    align: "left", valign: "middle"
  });

  slide.addText("A capability pack declares its own sections, roles, workflows and metrics. Five rules stop a pack from quietly widening its own authority.", {
    x: 0.6, y: 1.18, w: 8.8, h: 0.5,
    fontSize: 12.5, fontFace: BODY, color: theme.secondary,
    align: "left", valign: "top", lineSpacingMultiple: 1.2
  });

  const rules = [
    { num: "01", text: "Cannot raise a role's spending limit." },
    { num: "02", text: "Cannot claim a capability another pack already owns." },
    { num: "03", text: "Cannot use live data unless its readiness is established." },
    { num: "04", text: "Version-gated. A pack too new for the core will not load." },
    { num: "05", text: "Cannot review its own actions." }
  ];

  const cardXs = [0.60, 2.38, 4.16, 5.94, 7.72];
  const cardY = 1.85;

  for (let i = 0; i < rules.length; i++) {
    const cardX = cardXs[i];

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cardX, y: cardY, w: 1.66, h: 2.05,
      rectRadius: 0.16,
      fill: { color: theme.light },
      line: { color: theme.light, width: 0 }
    });

    slide.addShape(pres.shapes.OVAL, {
      x: cardX + 0.24, y: cardY + 0.22, w: 0.26, h: 0.26,
      fill: { color: theme.accent }
    });

    slide.addText(rules[i].num, {
      x: cardX + 0.24, y: cardY + 0.58, w: 1.2, h: 0.3,
      fontSize: 13, fontFace: HEAD, color: theme.accent, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(rules[i].text, {
      x: cardX + 0.20, y: cardY + 0.95, w: 1.28, h: 0.95,
      fontSize: 10.5, fontFace: BODY, color: theme.primary,
      align: "left", valign: "top", lineSpacingMultiple: 1.15
    });
  }

  slide.addText("Add a section without touching core code. It stays hidden from anyone without the permission, and the route refuses them even if they try it directly.", {
    x: 0.6, y: 4.18, w: 8.8, h: 0.6,
    fontSize: 12, fontFace: BODY, color: theme.secondary,
    align: "left", valign: "top", lineSpacingMultiple: 1.2
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("13", {
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
  pres.writeFile({ fileName: "slide-13-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
