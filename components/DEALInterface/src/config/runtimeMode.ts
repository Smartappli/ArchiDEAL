export function demoDataEnabled(mode: string, configured?: string) {
  return mode !== "production" && configured !== "false";
}

export const showDemoData = demoDataEnabled(
  import.meta.env.MODE,
  import.meta.env.VITE_ENABLE_DEMO_DATA,
);
