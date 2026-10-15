import { WelcomeHeading } from './WelcomeHeading';
import { RobotMascot } from './RobotMascot';
import { ProPlanBanner } from './ProPlanBanner';
import { ChatInput } from './ChatInput';
import { CategoryPills } from './CategoryPills';

export function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-56px)] pb-6 sm:pb-10 px-3 sm:px-4 w-full overflow-x-hidden">
      {/* Welcome Heading */}
      <WelcomeHeading />

      {/* Robot Mascot with Speech Bubbles */}
      <RobotMascot />

      {/* Pro Plan Banner — original compact width, independent of the
          widened message column */}
      <div className="w-full max-w-[720px]">
        <ProPlanBanner />
      </div>

      {/* Chat Input — same compact width as the banner above */}
      <div className="w-full max-w-[720px] px-1">
        <ChatInput />
      </div>

      {/* Category Pills */}
      <CategoryPills />
    </div>
  );
}
