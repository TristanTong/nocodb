export const getAppUrl = () => {
  const siteUrl =
    process.env.NC_PUBLIC_URL || `http://localhost:${process.env.PORT || 6080}`;

  return `${siteUrl}${process.env.NC_DASHBOARD_URL ?? '/dashboard'}`;
};
