const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'grid',
  index: 4,
  title: 'One app for the whole company'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("One app for the whole company", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  const tiles = [
    "Chat", "Documents & SOPs", "Tasks", "Calendar",
    "On-call", "Attendance", "Notifications", "Knowledge base"
  ];

  tiles.forEach((label, i) => {
    const col = i % 4;
    const row = Math.floor(i / 4);
    const x = 0.6 + col * 2.20;
    const y = 1.32 + row * 1.07;

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: y, w: 2.06, h: 0.95,
      fill: { color: theme.light },
      rectRadius: 0.16
    });
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x + 0.22, y: y + 0.22, w: 0.24, h: 0.24,
      fill: { color: theme.accent },
      rectRadius: 0.06
    });
    slide.addText(label, {
      x: x + 0.22, y: y + 0.50, w: 1.68, h: 0.34,
      fontSize: 12.5, fontFace: HEAD, bold: true,
      color: theme.primary, align: "left", valign: "middle"
    });
  });

  slide.addText("Plus two sections most people never see:", {
    x: 0.6, y: 3.46, w: 8.8, h: 0.32,
    fontSize: 13, fontFace: BODY,
    color: theme.secondary, align: "left", valign: "middle"
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.6, y: 3.86, w: 4.25, h: 1.0,
    fill: { color: theme.primary },
    rectRadius: 0.16
  });
  slide.addText("Operations", {
    x: 0.85, y: 3.98, w: 3.8, h: 0.34,
    fontSize: 14, fontFace: HEAD, bold: true,
    color: "FFFFFF", align: "left", valign: "middle"
  });
  slide.addText("Engine overview and governed workflow approvals.", {
    x: 0.85, y: 4.32, w: 3.8, h: 0.42,
    fontSize: 11.5, fontFace: BODY,
    color: theme.secondary, align: "left", valign: "top"
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.15, y: 3.86, w: 4.25, h: 1.0,
    fill: { color: theme.accent },
    rectRadius: 0.16
  });
  slide.addText("The Cockpit", {
    x: 5.40, y: 3.98, w: 3.8, h: 0.34,
    fontSize: 14, fontFace: HEAD, bold: true,
    color: "FFFFFF", align: "left", valign: "middle"
  });
  slide.addText("The owner's numbers. Managers and owners only, enforced server-side.", {
    x: 5.40, y: 4.32, w: 3.8, h: 0.42,
    fontSize: 11.5, fontFace: BODY,
    color: "FFFFFF", align: "left", valign: "top"
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("04", {
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
  pres.writeFile({ fileName: "slide-04-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
