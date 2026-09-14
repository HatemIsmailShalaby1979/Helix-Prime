const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  subtype: 'comparison',
  index: 11,
  title: 'Accounts, roles and limits'
};

const HEAD = "Trebuchet MS";
const BODY = "Calibri";

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("Accounts, roles and limits", {
    x: 0.6, y: 0.42, w: 8.8, h: 0.6,
    fontSize: 30, fontFace: HEAD, bold: true,
    color: theme.primary, align: "left", valign: "middle", fit: "shrink"
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.60, y: 1.35, w: 4.25, h: 3.45,
    rectRadius: 0.16,
    fill: { color: theme.light }
  });

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.15, y: 1.35, w: 4.25, h: 3.45,
    rectRadius: 0.16,
    fill: { color: theme.light }
  });

  slide.addText("How people sign in", {
    x: 0.88, y: 1.55, w: 3.7, h: 0.34,
    fontSize: 15, fontFace: HEAD, color: theme.primary, bold: true,
    align: "left", valign: "middle"
  });

  const signIn = [
    "A username and a domain, so one company is one tenant.",
    "Passwords hashed with scrypt, never stored in the clear.",
    "Opaque cookie sessions. No tokens to leak.",
    "A CSRF check on every write, not just the important ones.",
    "Lockout after repeated failures, and sessions that revoke the moment an account is disabled."
  ];

  for (let i = 0; i < signIn.length; i++) {
    slide.addText(signIn[i], {
      x: 0.88, y: 2.02 + i * 0.52, w: 3.7, h: 0.46,
      fontSize: 11.5, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top", lineSpacingMultiple: 1.15
    });
  }

  slide.addText("Who reaches what", {
    x: 5.43, y: 1.55, w: 3.7, h: 0.34,
    fontSize: 15, fontFace: HEAD, color: theme.primary, bold: true,
    align: "left", valign: "middle"
  });

  const roles = [
    { name: "Employee", desc: "Chat, documents, tasks, calendar and the punch clock." },
    { name: "Manager", desc: "All of that, plus operations, team views and memory review." },
    { name: "Owner", desc: "All of that, plus the cockpit, admin and the evidence export." }
  ];

  for (let i = 0; i < roles.length; i++) {
    const rowY = 2.02 + i * 0.86;

    slide.addText(roles[i].name, {
      x: 5.43, y: rowY, w: 3.7, h: 0.3,
      fontSize: 12.5, fontFace: HEAD, color: theme.accent, bold: true,
      align: "left", valign: "middle"
    });

    slide.addText(roles[i].desc, {
      x: 5.43, y: rowY + 0.30, w: 3.7, h: 0.5,
      fontSize: 11, fontFace: BODY, color: theme.secondary,
      align: "left", valign: "top", lineSpacingMultiple: 1.15
    });
  }

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("11", {
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
  pres.writeFile({ fileName: "slide-11-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
