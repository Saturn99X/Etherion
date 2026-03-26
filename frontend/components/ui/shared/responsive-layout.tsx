// RESPONSIVE GRID SYSTEMS
export const responsiveGrid = {
  dashboard: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6",
  sidebar: "flex flex-col lg:flex-row gap-6",
  cards: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4",
  forms: "grid grid-cols-1 md:grid-cols-2 gap-4"
};

// MOBILE-FIRST RESPONSIVE DESIGN
export const mobileFirst = {
  breakpoints: {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px'
  },
  containers: {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl'
  }
};
