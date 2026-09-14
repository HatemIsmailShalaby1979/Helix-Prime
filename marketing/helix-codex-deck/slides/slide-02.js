const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'toc',
  index: 2,
  title: "What's inside"
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("What's inside", {
    x: 0.6, y: 0.42, w: 8.0, h: 0.6,
    fontSize: 32, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  const cards = [
    { n: "01", t: "The problem", d: "Six subscriptions, rented data, and AI that only suggests." },
    { n: "02", t: "The platform", d: "Chat, docs, tasks, calendar, on-call and attendance in one place." },
    { n: "03", t: "The intelligence", d: "Nine agent roles, governed workflows, and a memory that improves with use." },
    { n: "04", t: "The offer", d: "Four tiers. Sample data is free. Live data is paid." }
  ];

  const positions = [
    { x: 0.6, y: 1.42 },
    { x: 5.15, y: 1.42 },
    { x: 0.6, y: 3.22 },
    { x: 5.15, y: 3.22 }
  ];

  cards.forEach((c, i) => {
    const p = positions[i];
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: p.x, y: p.y, w: 4.25, h: 1.58,
      fill: { color: theme.light },
      rectRadius: 0.2
    });
    slide.addText([
      { text: c.n + "   ", options: { color: theme.accent, bold: true, fontSize: 22, fontFace: HEAD } },
      { text: c.t, options: { color: theme.primary, bold: true, fontSize: 17, fontFace: HEAD } }
    ], {
      x: p.x + 0.28, y: p.y + 0.2, w: 3.75, h: 0.5,
      align: "left", valign: "middle"
    });
    slide.addText(c.d, {
      x: p.x + 0.28, y: p.y + 0.72, w: 3.75, h: 0.7,
      fontSize: 12.5, fontFace: BODY,
      color: theme.secondary, align: "left", valign: "top", lineSpacingMultiple: 1.2
    });
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("02", {
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
  pres.writeFile({ fileName: "slide-02-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
