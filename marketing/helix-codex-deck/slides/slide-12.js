const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'mixed',
  index: 12,
  title: 'Built for the phone in their pocket'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Built for the phone in their pocket", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle", fit: "shrink"
  });

  const rows = [
    {
      heading: "Installs from the browser",
      desc: "No app store, no review queue, no download to explain to staff."
    },
    {
      heading: "Works when the signal does not",
      desc: "The shell and the pages you last opened stay readable offline."
    },
    {
      heading: "One-handed by design",
      desc: "44 pixel tap targets and a bottom nav that sits under the thumb."
    },
    {
      heading: "Opens instantly",
      desc: "System fonts and no build step, so there is nothing to wait for."
    }
  ];

  for (let i = 0; i < rows.length; i++) {
    const rowY = 1.55 + i * 0.82;

    slide.addShape(pres.shapes.OVAL, {
      x: 0.62, y: rowY + 0.29, w: 0.18, h: 0.18,
      fill: { color: theme.accent }
    });

    slide.addText(rows[i].heading, {
      x: 1.00, y: rowY, w: 5.5, h: 0.32,
      fontSize: 13, fontFace: HEAD, color: theme.primary, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(rows[i].desc, {
      x: 1.00, y: rowY + 0.32, w: 5.5, h: 0.44,
      fontSize: 11.5, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top", lineSpacingMultiple: 1.15
    });
  }

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 7.35, y: 1.45, w: 1.75, h: 3.20,
    rectRadius: 0.22,
    fill: { color: theme.primary }
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 7.50, y: 1.62, w: 1.45, h: 2.86,
    rectRadius: 0.14,
    fill: { color: theme.light }
  });

  for (let i = 0; i < 4; i++) {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 7.65, y: 1.90 + i * 0.46, w: 1.15, h: 0.30,
      rectRadius: 0.08,
      fill: { color: i === 3 ? theme.accent : theme.secondary }
    });
  }

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("12", {
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
  pres.writeFile({ fileName: "slide-12-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
