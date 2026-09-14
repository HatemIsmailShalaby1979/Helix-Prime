const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'grid',
  index: 6,
  title: 'An AI organization, not a chatbot'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("An AI organization, not a chatbot", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  const agents = [
    { name: "SAMI", role: "Executive Coordinator / CEO" },
    { name: "SUBY", role: "OPS GM" },
    { name: "PHILI", role: "HR & Personnel GM" },
    { name: "WILI", role: "L&D GM" },
    { name: "MAYA", role: "Marketing GM" },
    { name: "LIZA", role: "Sales GM" },
    { name: "ANDY", role: "Compliance & Quality GM" },
    { name: "TOMY", role: "ICT GM" },
    { name: "NONO", role: "Fraud & Revenue Assurance GM" }
  ];

  const cols = [0.60, 3.55, 6.50];
  const rows = [1.35, 2.48, 3.61];

  agents.forEach((agent, i) => {
    const x = cols[i % 3];
    const y = rows[Math.floor(i / 3)];

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: y, w: 2.8, h: 1.0,
      fill: { color: theme.light },
      rectRadius: 0.16
    });
    slide.addText(agent.name, {
      x: x + 0.24, y: y + 0.16, w: 2.35, h: 0.34,
      fontSize: 15, fontFace: HEAD, bold: true,
      color: theme.accent, align: "left", valign: "middle"
    });
    slide.addText(agent.role, {
      x: x + 0.24, y: y + 0.52, w: 2.35, h: 0.36,
      fontSize: 11, fontFace: BODY,
      color: theme.secondary, align: "left", valign: "middle"
    });
  });

  slide.addText("Nine roles with a named responsibility, an approval limit and an owner to escalate to.", {
    x: 0.6, y: 4.72, w: 8.8, h: 0.26,
    fontSize: 11.5, fontFace: BODY,
    color: theme.secondary, align: "left", valign: "middle"
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("06", {
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
  pres.writeFile({ fileName: "slide-06-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
