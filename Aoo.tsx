import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ChatMessage,
  TimeStampedSegment,
  Messages,
  OCRSegment,
} from "./types";
import * as NativeService from "./native-service";
import * as TVWindow from "./tv-window";
import * as OCR_Service from "./ocr-service";
import ChatOverlay from "./chat-overlay";
import MockAnswerDisplay from "./mock-answer-display";
import { KeyCode } from "./keycodes";
import EyeIcon from "./eye-icon";

function App() {
  const maxAgeMinutes = 1;

  const [qwenAnswer, setQwenAnswer] = useState<string>("");
  const [subtitles, setSubtitles] = useState<TimeStampedSegment[]>([]);
  const [OCR, setOCR] = useState<OCRSegment[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isChatOverlayVisible, setIsChatOverlayVisible] =
    useState<boolean>(false);
  const [isResettingHistory, setIsResettingHistory] = useState<boolean>(false);

  const [NativeMessage, setNativeMessage] = useState<Messages>({
    CC: "",
    OCR: "",
    sys_prompt: "",
    usr_request: "",
  });

  const latestRequestIdRef = useRef(0);

  const rightButtonSystemPrompt =
    "I am an user watching TV (streaming of programs such as sports and news content) and I want to be recommended certain utterances in text that I could ask my voice assistant to fulfill. You will be given text information in [CC] and [OCR], use that information to generate the utterances. Example: I am watching a soccer game being played and the [OCR] and [CC] information reveals that, a possible utterance could be: 'Give me the latest standings of the winning team'. Could you generate more? Use the [USER_REQUEST] information to identify how many utterances to generate, just extract that information from [USER_REQUEST], nothing else. Please provide your answer in a numbered list in the following format: Answer: [utterance 1, utterance 2, utterance 3,...].";

  const format_subtitles = (str: string): string => {
    let pre_format_str = str
      .replace(/[\r\n]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    for (let i = 0; i < 3; i++) {
      pre_format_str = removeRepeatedSequences(pre_format_str);
    }

    return pre_format_str;
  };

  const removeRepeatedSequences = (text: string): string => {
    const words = text.split(" ");
    const sequenceLength = 2;

    for (let len = sequenceLength; len <= words.length / 2; len++) {
      let i = 0;
      while (i + len * 2 <= words.length) {
        const seq1 = words.slice(i, i + len).join(" ").toLowerCase();
        const seq2 = words
          .slice(i + len, i + len * 2)
          .join(" ")
          .toLowerCase();

        if (seq1 === seq2) {
          words.splice(i + len, len);
        } else {
          i++;
        }
      }
    }

    return words.join(" ");
  };

  const handleNewSubtitles = useCallback(
    (newSub: TimeStampedSegment) => {
      if (isResettingHistory) {
        console.log("subtitles dropped: resetting history in progress");
        return;
      }

      setSubtitles((prevSubtitles) => {
        const latestTimestamp = Number(newSub.timestamp);
        const cutoffTime = latestTimestamp - maxAgeMinutes * 60 * 1000;

        return [...prevSubtitles, newSub].filter(
          (segment) => Number(segment.timestamp) >= cutoffTime
        );
      });
    },
    [isResettingHistory]
  );

  const handleNewOCR = useCallback((newOCR: OCRSegment) => {
    setOCR((prevOCR) => {
      const latestTimestamp = Number(newOCR.timestamp);
      const cutoffTime = latestTimestamp - maxAgeMinutes * 60 * 1000;

      return [...prevOCR, newOCR].filter(
        (segment) => segment.timestamp >= cutoffTime
      );
    });
  }, []);

  const resetHistory = useCallback(() => {
    setIsResettingHistory(true);
    setSubtitles([]);
    setOCR([]);
    setChatMessages([]);
    setQwenAnswer("");
    setIsChatOverlayVisible(false);
    setIsResettingHistory(false);
  }, []);

  const showLatestRequestOnly = useCallback((requestText: string) => {
    setChatMessages([
      {
        role: "user",
        content: requestText,
      },
    ]);
  }, []);

  const runRequest = useCallback(
    async (requestText: string, systemPromptOverride?: string) => {
      const trimmedRequest = requestText.trim();
      if (!trimmedRequest) return;

      latestRequestIdRef.current += 1;
      const requestId = latestRequestIdRef.current;

      setIsChatOverlayVisible(true);
      showLatestRequestOnly(trimmedRequest);
      setQwenAnswer("");

      const outgoingMessage: Messages = {
        ...NativeMessage,
        usr_request: trimmedRequest,
        sys_prompt: systemPromptOverride ?? NativeMessage.sys_prompt,
      };

      console.log("Sending request:", outgoingMessage);

      const data = await OCR_Service.getOCRResponse(outgoingMessage);

      // Ignore stale responses from older requests
      if (requestId !== latestRequestIdRef.current) {
        console.log("Ignoring stale response for request:", trimmedRequest);
        return;
      }

      const cleanedAnswer = data?.trim() || "";
      const finalAnswer = cleanedAnswer.toLowerCase().startsWith("answer:")
        ? cleanedAnswer.slice(7).trim()
        : cleanedAnswer;

      setQwenAnswer(finalAnswer || "");
    },
    [NativeMessage, showLatestRequestOnly]
  );

  const onExit = useCallback(async () => {
    console.log("Exiting...");
    await NativeService.stop();
  }, []);

  const handleKeypress = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    async (event: { keyCode: any }) => {
      switch (event.keyCode) {
        case KeyCode.RIGHT: {
          await runRequest(
            "Provide me 5 utterance recommendations",
            rightButtonSystemPrompt
          );
          break;
        }
        case KeyCode.LEFT: {
          console.log("Reset History");
          resetHistory();
          break;
        }
        case KeyCode.CHANNEL_UP: {
          TVWindow.tuneUp();
          resetHistory();
          break;
        }
        case KeyCode.CHANNEL_DOWN: {
          TVWindow.tuneDown();
          resetHistory();
          break;
        }
        case KeyCode.GUIDE: {
          resetHistory();
          break;
        }
        case KeyCode.MEDIA_PLAY_PAUSE: {
          setIsChatOverlayVisible(!isChatOverlayVisible);
          break;
        }
        case KeyCode.BACK:
        case KeyCode.EXIT:
          onExit();
          break;
        default:
          console.log("Unhandled Key Pressed:", event.keyCode);
          break;
      }
    },
    [
      isChatOverlayVisible,
      onExit,
      resetHistory,
      rightButtonSystemPrompt,
      runRequest,
    ]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeypress);
    window.addEventListener("visibilitychange", onExit);
    window.addEventListener("pause", onExit);

    window.tizen?.tvinputdevice.registerKeyBatch([
      "ChannelUp",
      "ChannelDown",
      "Guide",
      "Exit",
      "MediaPlayPause",
    ]);

    return () => {
      window.removeEventListener("keydown", handleKeypress);
      window.removeEventListener("visibilitychange", onExit);
      window.removeEventListener("pause", onExit);
    };
  }, [handleKeypress, onExit]);

  useEffect(() => {
    console.log("Showing TVWindow...");
    TVWindow.show();

    NativeService.start(async (result) => {
      switch (result.type) {
        case "subtitle": {
          const sub = format_subtitles(result.data);
          const newSub: TimeStampedSegment = {
            timestamp: result.timestamp,
            playbackTime: result.time_playback,
            content: sub,
          };

          handleNewSubtitles(newSub);
          break;
        }
        case "user": {
          console.log("handle user prompt:", result.data);
          await runRequest(result.data);
          break;
        }
        case "ocr": {
          console.log("handle ocr data");
          const ocr = format_subtitles(result.data);
          const newOCR: OCRSegment = {
            timestamp: Date.now(),
            content: ocr,
          };

          handleNewOCR(newOCR);
          break;
        }
        default:
          break;
      }
    });
  }, [handleNewOCR, handleNewSubtitles, runRequest]);

  useEffect(() => {
    console.log("Set System Prompt");
    const system_prompt =
      "Your are an agent that is designed to give answers to a TV user. The inputs are [OCR] and [CC] and [USER_REQUEST]. Based on the provided [USER_REQUEST], identify if you can provide an answer based on [OCR] and [CC], if not, create a simple query for web search of at most 5 words. Use the query with the provided websearch tool, retrieve the information and summarize in [ANSWER] and output in the following format:\n Answer: [ANSWER]. Do not return anything else";

    setNativeMessage((prev) => ({
      ...prev,
      sys_prompt: system_prompt,
    }));
  }, []);

  useEffect(() => {
    const fullCC = format_subtitles(
      subtitles.map((segment) => segment.content).join(" ")
    );

    setNativeMessage((prev) => ({
      ...prev,
      CC: fullCC,
    }));
  }, [subtitles]);

  useEffect(() => {
    const fullOCR = format_subtitles(OCR.map((segment) => segment.content).join(" "));

    setNativeMessage((prev) => ({
      ...prev,
      OCR: fullOCR,
    }));
  }, [OCR]);

  const mockedUI = window.tizen === undefined;

  return (
    <div className="container">
      <EyeIcon enabled={true} />
      <ChatOverlay
        messages={
          mockedUI
            ? [
                { role: "user", content: "User asks a question." },
                {
                  role: "assistant",
                  content:
                    "Lorem ipsum odor amet, consectetuer adipiscing elit. Nullam tristique auctor ut class lectus turpis. Quis nibh sit facilisi eget erat ultricies massa. Nisi natoque mi commodo consequat nunc ac. ",
                },
                {
                  role: "user",
                  content: "The quick brown fox jumped over the lazy dog",
                },
                {
                  role: "assistant",
                  content:
                    "Massa mattis lectus ultricies himenaeos commodo tincidunt lorem. Et tincidunt rutrum dis porta porttitor. Proin imperdiet maecenas mus; vulputate nam condimentum maecenas magnis penatibus.",
                },
              ]
            : chatMessages
        }
        textInProgress={mockedUI ? "User question in progress" : ""}
        isSpeechEnabled={true}
        isVisible={mockedUI ? true : isChatOverlayVisible}
      />
      <MockAnswerDisplay
        content={qwenAnswer}
        isVisible={isChatOverlayVisible}
      />
    </div>
  );
}

export default App;