const redirectedPaths = new Set([
  "/privacy",
  "/best-wine-gifts-for-clients",
  "/guides/client-wine-gifts",
  "/corporate-wine-gifts-uk",
  "/guides/christmas-wine-gifts-for-clients",
  "/guides/wine-gifts-for-christmas",
  "/guides/thank-you-wine-gifts",
  "/guides/wine-gifts-for-thank-you",
  "/wine-for-corporate-events",
  "/guides/wine-tasting-corporate-event",
  "/guides/wine-gift-baskets-uk",
  "/guides/luxury-wine-gifts-for-clients",
  "/staff-wine-gifts-uk",
  "/supplier-application",
]);

const sitemapStaticRoutes = [
  "/",
  "/about",
  "/affiliate-disclosure",
  "/client-wine-gifts",
  "/client-christmas-gifts-uk",
  "/corporate-christmas-wine-gifts",
  "/corporate-gifting-ideas-uk",
  "/corporate-hampers-uk",
  "/corporate-wine-gifts",
  "/corporate-wine-tasting-events",
  "/editorial-policy",
  "/event-planner",
  "/event-wine-planning-uk",
  "/example-premium-brief-pack",
  "/example-premium-event-pack",
  "/faq",
  "/gift-planner",
  "/guides",
  "/premium-client-gifts-uk",
  "/premium-pack",
  "/pricing",
  "/privacy-policy",
  "/responsible-drinking",
  "/staff-wine-gifts",
  "/submit-supplier",
  "/supplier-directory",
  "/supplier-partnerships",
  "/suppliers",
  "/terms",
  "/thank-you-gifts-for-clients",
  "/uk-wine-gift-supplier-comparison",
];

const sitemapGuideRoutes = [
  "/guides/best-client-wine-gifts",
  "/guides/best-wine-accessories-for-gifts",
  "/guides/best-wine-gifts-under-100",
  "/guides/best-wine-gifts-under-25",
  "/guides/best-wine-gifts-under-50",
  "/guides/business-gift-wine-etiquette",
  "/guides/champagne-gifts-for-clients",
  "/guides/christmas-corporate-wine-gifts",
  "/guides/client-gift-policy-checklist",
  "/guides/client-gifting-etiquette-uk",
  "/guides/client-thank-you-wine-gifts",
  "/guides/corporate-event-wine-planning",
  "/guides/corporate-gift-ideas-for-clients",
  "/guides/corporate-gifting-recipient-csv-template",
  "/guides/corporate-wine-gifts-uk",
  "/guides/corporate-wine-gifts-under-100",
  "/guides/corporate-wine-gifts-under-50",
  "/guides/corporate-wine-hampers",
  "/guides/corporate-wine-tasting-london",
  "/guides/english-sparkling-corporate-gifts",
  "/guides/food-and-wine-hampers",
  "/guides/how-much-to-spend-on-client-gifts",
  "/guides/luxury-corporate-wine-gifts",
  "/guides/luxury-wine-hampers-uk",
  "/guides/non-alcoholic-client-gifts",
  "/guides/personalised-wine-gifts",
  "/guides/red-wine-gifts-for-clients",
  "/guides/staff-wine-gifts",
  "/guides/virtual-wine-tasting-for-teams",
  "/guides/white-wine-gifts-for-clients",
  "/guides/wine-gift-hampers-uk",
  "/guides/wine-gifts-for-accountancy-firms",
  "/guides/wine-gifts-for-agencies",
  "/guides/wine-gifts-for-customers",
  "/guides/wine-gifts-for-events",
  "/guides/wine-gifts-for-law-firms",
  "/guides/wine-gifts-for-new-business",
  "/guides/wine-gifts-for-sales-teams",
  "/guides/wine-tasting-team-building",
];

const sitemapRoutes = [...sitemapStaticRoutes, ...sitemapGuideRoutes];
const duplicates = sitemapRoutes.filter((route, index) => sitemapRoutes.indexOf(route) !== index);
const redirectedInSitemap = sitemapRoutes.filter((route) => redirectedPaths.has(route));

if (duplicates.length || redirectedInSitemap.length) {
  console.error("SEO route check failed.");
  if (duplicates.length) {
    console.error("Duplicate sitemap routes:", [...new Set(duplicates)].join(", "));
  }
  if (redirectedInSitemap.length) {
    console.error("Redirected routes in sitemap:", redirectedInSitemap.join(", "));
  }
  process.exit(1);
}

console.log(`SEO route check passed for ${sitemapRoutes.length} sitemap routes.`);
