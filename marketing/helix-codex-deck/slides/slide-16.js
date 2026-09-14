const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'summary',
  subtype: 'summary',
  index: 16,
  title: 'Start with one academy.'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  slide.addText("Start with one academy.", {
    x: 0.75, y: 0.90, w: 8.5, h: 0.9,
    fontSize: 44, fontFace: HEAD, color: "FFFFFF", bold: true,
    align: "left", valign: "middle"
  });

  slide.addText("Scoach Academy Hub is the first deployment. A working pilot in weeks, not quarters.", {
    x: 0.75, y: 1.85, w: 7.6, h: 0.5,
    fontSize: 15, fontFace: BODY, color: theme.secondary,
    align: "left", valign: "middle"
  });

  const steps = [
    { num: "1", heading: "Run the pilot", desc: "Sixty days, your data, your hardware, no migration project." },
    { num: "2", heading: "Add your capability pack", desc: "The sections and metrics your business actually uses, not a generic template." },
    { num: "3", heading: "Own the result", desc: "The code, the data and the audit trail stay with you." }
  ];

  for (let i = 0; i < steps.length; i++) {
    const rowY = 2.70 + i * 0.72;

    slide.addShape(pres.shapes.OVAL, {
      x: 0.78, y: rowY, w: 0.34, h: 0.34,
      fill: { color: theme.accent }
    });

    slide.addText(steps[i].num, {
      x: 0.78, y: rowY, w: 0.34, h: 0.34,
      fontSize: 12, fontFace: BODY, color: "FFFFFF", bold: true,
      align: "center", valign: "middle"
    });

    slide.addText(steps[i].heading, {
      x: 1.30, y: rowY, w: 7.6, h: 0.32,
      fontSize: 13.5, fontFace: HEAD, color: "FFFFFF", bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(steps[i].desc, {
      x: 1.30, y: rowY + 0.30, w: 7.6, h: 0.40,
      fontSize: 11.5, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top"
    });
  }

  slide.addText("Hatem Shalaby   ·   Helix Codex OS   ·   github.com/HatemIsmailShalaby1979/Helix-Prime", {
    x: 0.75, y: 4.92, w: 8.5, h: 0.34,
    fontSize: 12, fontFace: BODY, color: theme.secondary,
    align: "left", valign: "middle"
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("16", {
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
  pres.writeFile({ fileName: "slide-16-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
