import { Composition } from "remotion";
import { ExtendingFramework } from "./compositions/ExtendingFramework";
import { GettingStarted } from "./compositions/GettingStarted";
import { PythonSDK } from "./compositions/PythonSDK";
import { TypeScriptSDK } from "./compositions/TypeScriptSDK";

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
      <Composition
        id="GettingStarted"
        component={GettingStarted}
        durationInFrames={1860}
        fps={60}
        width={1920}
        height={1080}
      />
      <Composition
        id="PythonSDK"
        component={PythonSDK}
        durationInFrames={1590}
        fps={60}
        width={1920}
        height={1080}
      />
      <Composition
        id="TypeScriptSDK"
        component={TypeScriptSDK}
        durationInFrames={1590}
        fps={60}
        width={1920}
        height={1080}
      />
    </>
  );
};
