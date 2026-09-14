const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'data',
  index: 8,
  title: "The owner's cockpit"
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("The owner's cockpit", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle"
  });

  const metrics = [
    { value: "148", label: "Active athletes" },
    { value: "62,400", label: "MRR (USD)" },
    { value: "78%", label: "Attendance (7d)" },
    { value: "9", label: "At-risk athletes" },
    { value: "71%", label: "Facility utilisation" }
  ];

  const xs = [0.60, 2.38, 4.16, 5.94, 7.72];

  metrics.forEach((metric, i) => {
    const x = xs[i];

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: 1.55, w: 1.66, h: 1.35,
      fill: { color: theme.light },
      rectRadius: 0.16
    });
    slide.addText(metric.value, {
      x: x + 0.12, y: 1.77, w: 1.42, h: 0.5,
      fontSize: 24, fontFace: HEAD, bold: true,
      color: theme.accent, align: "center", valign: "middle"
    });
    slide.addText(metric.label, {
      x: x + 0.12, y: 2.33, w: 1.42, h: 0.45,
      fontSize: 10, fontFace: BODY,
      color: theme.secondary, align: "center", valign: "top",
      lineSpacingMultiple: 1.15
    });
  });

  slide.addText("From the Sports Academy capability pack - the first vertical pack.", {
    x: 0.6, y: 3.12, w: 8.8, h: 0.3,
    fontSize: 12, fontFace: BODY,
    color: theme.secondary, align: "left", valign: "middle"
  });

  const notes = [
    "Managers and owners only. The check runs at the route, again in the service, and again at the policy seam.",
    "Simulated data is labelled on every card. Nothing on this screen pretends to be live."
  ];
  const noteYs = [3.62, 4.12];

  notes.forEach((note, i) => {
    const y = noteYs[i];

    slide.addShape(pres.shapes.OVAL, {
      x: 0.62, y: y + 0.12, w: 0.18, h: 0.18,
      fill: { color: theme.accent }
    });
    slide.addText(note, {
      x: 1.0, y: y, w: 8.3, h: 0.42,
      fontSize: 12.5, fontFace: BODY,
      color: theme.primary, align: "left", valign: "middle"
    });
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("08", {
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
  pres.writeFile({ fileName: "slide-08-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
