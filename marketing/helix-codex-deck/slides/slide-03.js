const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'text',
  index: 3,
  title: 'Three things operations teams are tired of'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Three things operations teams are tired of", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  const rows = [
    {
      n: "1",
      t: "Your stack is six subscriptions",
      d: "Chat in one app, documents in another, tasks somewhere else. Nothing talks to anything, and you pay for all of it."
    },
    {
      n: "2",
      t: "Your data lives in someone else's cloud",
      d: "The roster, the CRM, the payroll export. All rented, all out of your hands, all priced per seat, forever."
    },
    {
      n: "3",
      t: "Your AI only suggests",
      d: "It writes a tidy paragraph. Then a person retypes it into the system that actually does the work."
    }
  ];

  rows.forEach((r, i) => {
    const y = 1.50 + i * 1.18;

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.6, y: y, w: 8.8, h: 1.0,
      fill: { color: theme.light },
      rectRadius: 0.16
    });

    slide.addShape(pres.shapes.OVAL, {
      x: 0.82, y: y + 0.24, w: 0.52, h: 0.52,
      fill: { color: theme.accent }
    });
    slide.addText(r.n, {
      x: 0.82, y: y + 0.24, w: 0.52, h: 0.52,
      fontSize: 18, fontFace: HEAD, bold: true, color: "FFFFFF",
      align: "center", valign: "middle"
    });

    slide.addText(r.t, {
      x: 1.56, y: y + 0.13, w: 7.6, h: 0.4,
      fontSize: 16, fontFace: HEAD, bold: true,
      color: theme.primary, align: "left", valign: "middle"
    });

    slide.addText(r.d, {
      x: 1.56, y: y + 0.52, w: 7.62, h: 0.42,
      fontSize: 12.5, fontFace: BODY,
      color: theme.secondary, align: "left", valign: "top"
    });
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("03", {
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
  pres.writeFile({ fileName: "slide-03-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
