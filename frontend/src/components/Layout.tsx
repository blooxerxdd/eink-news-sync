import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/runs", label: "Runs" },
  { to: "/sources", label: "Source" },
  { to: "/digests", label: "Digests" },
  { to: "/devices", label: "Devices" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  return (
    <div className="min-h-screen font-sans text-ink">
      <header className="border-b border-rule bg-paper/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <p className="font-serif text-2xl tracking-tight">eink-news-sync</p>
            <p className="text-xs uppercase tracking-[0.18em] text-forest">LAN only · do not expose</p>
          </div>
          <nav className="flex flex-wrap gap-1">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  `rounded-full px-3 py-1.5 text-sm ${
                    isActive ? "bg-ink text-paper" : "text-ink/80 hover:bg-rule/70"
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
