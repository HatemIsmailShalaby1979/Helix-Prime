const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'comparison',
  index: 10,
  title: 'The governance is real, not a slide'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("The governance is real, not a slide", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle", fit: "shrink"
  });

  const cards = [
    {
      x: 0.60, y: 1.40,
      heading: "Fail closed",
      desc: "When a control cannot be checked, the action is denied and an error is raised. It never quietly carries on."
    },
    {
      x: 5.15, y: 1.40,
      heading: "Every action is a node",
      desc: "Each write carries its tenant, classification, provenance and a correlation id that survives every boundary."
    },
    {
      x: 0.60, y: 3.15,
      heading: "Simulated stays labelled",
      desc: "Synthetic, historical and live data look different on screen. Always."
    },
    {
      x: 5.15, y: 3.15,
      heading: "Improvement is a proposal",
      desc: "Nothing self-deploys. It takes evaluation, review, approval, a version and a rollback path."
    }
  ];

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: card.x, y: card.y, w: 4.25, h: 1.6,
      rectRadius: 0.16,
      fill: { color: theme.light }
    });

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: card.x + 0.28, y: card.y + 0.26, w: 0.22, h: 0.22,
      rectRadius: 0.05,
      fill: { color: theme.accent }
    });

    slide.addText(card.heading, {
      x: card.x + 0.62, y: card.y + 0.18, w: 3.4, h: 0.36,
      fontSize: 15, fontFace: HEAD, color: theme.primary, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(card.desc, {
      x: card.x + 0.28, y: card.y + 0.66, w: 3.7, h: 0.8,
      fontSize: 11.5, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top", lineSpacingMultiple: 1.2
    });
  }

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("10", {
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
  pres.writeFile({ fileName: "slide-10-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
