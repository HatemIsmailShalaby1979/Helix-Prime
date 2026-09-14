const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';

const theme = {
  primary: "2B2D42",
  secondary: "8D99AE",
  accent: "EF233C",
  light: "EDF2F4",
  bg: "FFFFFF"
};

const SLIDE_COUNT = 16;

for (let i = 1; i <= SLIDE_COUNT; i++) {
  const num = String(i).padStart(2, '0');
  const slideModule = require(`./slide-${num}.js`);
  slideModule.createSlide(pres, theme);
  console.log(`compiled slide ${num} — ${slideModule.slideConfig.title}`);
}

pres.writeFile({ fileName: './output/Helix_Codex_App_Deck.pptx' })
  .then((fileName) => {
    console.log(`\nwrote ${fileName}`);
  })
  .catch((err) => {
    console.error('compile failed:', err);
    process.exit(1);
  });
