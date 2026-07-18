"use client";

import { createReactBlockSpec } from "@blocknote/react";
import { Check, Edit3, Sigma } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { BlockMath } from "react-katex";
import "katex/dist/katex.min.css";

type MathBlockRenderProps = {
  block: { props: { formula: string } };
  editor: {
    updateBlock: (
      block: MathBlockRenderProps["block"],
      update: { props: { formula: string } },
    ) => void;
  };
};

function MathBlockView(props: MathBlockRenderProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [localFormula, setLocalFormula] = useState(props.block.props.formula);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(
        textareaRef.current.value.length,
        textareaRef.current.value.length,
      );
    }
  }, [isEditing]);

  const handleSave = () => {
    props.editor.updateBlock(props.block, {
      props: { formula: localFormula },
    });
    setIsEditing(false);
  };

  return (
    <div className="theme-panel-muted group hover:bg-surface-2 relative my-4 w-full p-4 transition-all">
      <div className="absolute top-3 right-3 z-10 hidden items-center gap-2 group-hover:flex">
        {isEditing ? (
          <button
            onClick={handleSave}
            className="border-success/30 bg-success/10 text-success hover:bg-success/20 flex h-8 w-8 items-center justify-center rounded-lg border transition-colors"
            title="Save formula"
          >
            <Check size={14} />
          </button>
        ) : (
          <button
            onClick={() => setIsEditing(true)}
            className="border-glass-border bg-surface-1 text-muted-foreground hover:bg-surface-2 hover:text-primary flex h-8 w-8 items-center justify-center rounded-lg border transition-colors"
            title="Edit formula"
          >
            <Edit3 size={14} />
          </button>
        )}
      </div>

      <div className="flex w-full flex-col">
        {isEditing ? (
          <div className="flex flex-col gap-3">
            <div className="text-muted-foreground/50 flex items-center gap-2 px-1 text-[10px] font-bold tracking-widest uppercase">
              <Sigma size={10} />
              LaTeX Equation Editor
            </div>
            <textarea
              ref={textareaRef}
              value={localFormula}
              onChange={(e) => setLocalFormula(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  handleSave();
                }
                if (e.key === "Escape") {
                  setLocalFormula(props.block.props.formula);
                  setIsEditing(false);
                }
              }}
              className="border-glass-border bg-surface-2/60 text-foreground placeholder:text-muted-foreground/30 focus:border-primary/50 min-h-[80px] w-full rounded-xl border p-4 font-mono text-sm transition-all outline-none"
              placeholder="Type your LaTeX here... (e.g. \sum_{i=1}^{n} i^3)"
            />
            <div className="text-muted-foreground/40 px-1 text-[10px] italic">
              Press Ctrl+Enter to save • Esc to cancel
            </div>
          </div>
        ) : (
          <div
            className="flex min-h-[60px] cursor-pointer items-center justify-center overflow-x-auto py-4"
            onDoubleClick={() => setIsEditing(true)}
          >
            <div className="text-foreground scale-110 lg:scale-125">
              {props.block.props.formula ? (
                <BlockMath math={props.block.props.formula} />
              ) : (
                <span className="text-muted-foreground/30 text-sm italic">Empty Equation</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export const MathBlock = createReactBlockSpec(
  {
    type: "math",
    propSchema: {
      formula: {
        default: "e = mc^2",
      },
    },
    content: "none",
  },
  {
    render: (props) => <MathBlockView {...(props as MathBlockRenderProps)} />,
  },
);
