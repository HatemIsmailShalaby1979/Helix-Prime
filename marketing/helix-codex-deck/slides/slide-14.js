const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'comparison',
  index: 14,
  title: 'Options'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Options", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, color: theme.primary, bold: true,
    align: "left", valign: "middle"
  });

  const tiers = [
    { name: "Community", price: "$0", desc: "One tenant, sample data, self-hosted on your own machine." },
    { name: "Helix Cloud", price: "$9", desc: "Per seat, per month, billed annually. Minimum five seats." },
    { name: "Capability Packs", price: "$49–$499", desc: "Per month, or $1,500 to $5,000 perpetual." },
    { name: "Enterprise", price: "$15k–$50k", desc: "Per year. Deployment, onboarding and support." }
  ];

  const cardXs = [0.60, 2.82, 5.04, 7.26];
  const cardY = 1.40;

  for (let i = 0; i < tiers.length; i++) {
    const cardX = cardXs[i];

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cardX, y: cardY, w: 2.06, h: 2.55,
      rectRadius: 0.16,
      fill: { color: theme.light },
      line: { color: theme.light, width: 0 }
    });

    slide.addText(tiers[i].name, {
      x: cardX + 0.22, y: cardY + 0.20, w: 1.62, h: 0.32,
      fontSize: 14, fontFace: HEAD, color: theme.primary, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(tiers[i].price, {
      x: cardX + 0.22, y: cardY + 0.58, w: 1.62, h: 0.42,
      fontSize: 19, fontFace: HEAD, color: theme.accent, bold: true,
      align: "left", valign: "middle"
    });

    slide.addShape(pres.shapes.LINE, {
      x: cardX + 0.22, y: cardY + 1.10, w: 1.62, h: 0,
      line: { color: theme.light, width: 1 }
    });

    slide.addText(tiers[i].desc, {
      x: cardX + 0.22, y: cardY + 1.22, w: 1.62, h: 1.15,
      fontSize: 10.5, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top", lineSpacingMultiple: 1.18
    });
  }

  slide.addText("The boundary is simple: sample data is free, live data is paid.", {
    x: 0.6, y: 4.25, w: 8.8, h: 0.4,
    fontSize: 12.5, fontFace: BODY, color: theme.primary,
    align: "left", valign: "middle"
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("14", {
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
  pres.writeFile({ fileName: "slide-14-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
