import { Composition } from "remotion";
import { ExtendingFramework } from "./compositions/ExtendingFramework";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ExtendingFramework"
        component={ExtendingFramework}
        durationInFrames={1500}
        fps={60}
        width={1920}
        height={1080}
      />
    </>
  );
};
