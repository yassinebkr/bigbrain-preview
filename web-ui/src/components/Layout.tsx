import { AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { Sidebar, MobileMenuButton } from './Sidebar';
import { TopBar } from './TopBar';
import { SidebarPanel } from './SidebarPanel';
import { CommandPalette } from './CommandPalette';
import { ActivityStrip } from './ActivityStrip';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { commandPaletteOpen, theme, view } = useAppStore();
  const isWorkspace = view === 'workspace';

  return (
    <div
      data-theme={theme}
      className="flex w-full h-screen overflow-hidden font-plus"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      {/* Left Sidebar - Desktop always visible, Mobile is drawer */}
      <Sidebar />

      {/* Main Content Area */}
      <div
        className="flex flex-col flex-1 h-screen overflow-hidden ml-0 md:ml-[52px]"
      >
        {/* Top Bar */}
        <TopBar>
          <MobileMenuButton />
        </TopBar>
        <ActivityStrip />

        {/* Main Content */}
        <main className="flex-1 overflow-hidden relative">
          <div className={isWorkspace ? "w-full h-full" : "max-w-[720px] md:max-w-[1200px] mx-auto w-full px-3 sm:px-4 md:px-6 h-full"}>
            {children}
          </div>
        </main>
      </div>

      {/* Sidebar Panel Overlay - uses AnimatePresence internally */}
      <SidebarPanel />

      {/* Command Palette Overlay */}
      <AnimatePresence>
        {commandPaletteOpen && <CommandPalette />}
      </AnimatePresence>
    </div>
  );
}
