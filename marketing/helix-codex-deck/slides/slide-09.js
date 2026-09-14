const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'timeline',
  index: 9,
  title: 'Every person gets a memory that improves with use'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Every person gets a memory that improves with use", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle", fit: "shrink"
  });

  const steps = [
    "Propose an improvement",
    "Evaluate it against history",
    "See the evidence",
    "A human approves",
    "Versioned and reversible"
  ];

  for (let i = 0; i < steps.length; i++) {
    const rowY = 1.40 + i * 0.70;

    slide.addShape(pres.shapes.OVAL, {
      x: 0.65, y: rowY + 0.01, w: 0.32, h: 0.32,
      fill: { color: theme.accent }
    });

    slide.addText(steps[i], {
      x: 1.15, y: rowY, w: 3.9, h: 0.34,
      fontSize: 13.5, fontFace: HEAD, color: theme.primary, bold: true,
      align: "left", valign: "middle"
    });
  }

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.30, y: 1.35, w: 4.10, h: 3.55,
    rectRadius: 0.16,
    fill: { color: theme.light }
  });

  slide.addText("What the reviewer actually sees", {
    x: 5.55, y: 1.55, w: 3.6, h: 0.34,
    fontSize: 13, fontFace: HEAD, color: theme.primary, bold: true,
    align: "left", valign: "middle"
  });

  const evidence = [
    "The baseline rate before the change.",
    "The candidate rate after it.",
    "The difference between the two.",
    "How many historical cases were used.",
    "How many simulated cases were used."
  ];

  for (let i = 0; i < evidence.length; i++) {
    slide.addText(evidence[i], {
      x: 5.55, y: 2.00 + i * 0.52, w: 3.6, h: 0.42,
      fontSize: 11.5, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top", lineSpacingMultiple: 1.15
    });
  }

  slide.addText("Nothing applies itself. A user's own approval is never enough to make a rule company-wide \u2014 that takes a second, independent approver.", {
    x: 0.6, y: 4.62, w: 8.8, h: 0.38,
    fontSize: 12, fontFace: BODY, color: theme.primary,
    align: "left", valign: "top", lineSpacingMultiple: 1.2
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("09", {
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
  pres.writeFile({ fileName: "slide-09-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
