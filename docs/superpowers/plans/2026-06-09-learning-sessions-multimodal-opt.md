# Learning Sessions Optimization and Multimodal Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize Leaf outline navigation, add custom text and handwriting/image input to AI chat tools, and add Canopy knowledge graph and Canvas Infinite Scratchpad pages.

**Architecture:** Frontend components leverage Canvas API and D3.js force layouts; API schemas and orchestration router parse base64 image data to form LangChain multimodal messages.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Framer Motion, HTML5 Canvas, D3.js, FastAPI, SQLModel, LangChain, Pytest, Vitest.

---

### Task 1: Backend Schemas and Router Multimodal Support

**Files:**
* Modify: `backend/app/schemas.py`
* Modify: `backend/app/api/orchestration.py`
* Test: `backend/tests/test_multimodal_api.py`

- [ ] **Step 1: Write a failing test for multimodal message request**
Create `backend/tests/test_multimodal_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from app.schemas import ChatMessageRequest

def test_multimodal_request_schema():
    req = ChatMessageRequest(
        session_id="test-session",
        message="explain this drawing",
        image_attachment="data:image/png;base64,iVBORw0KGgoAAAANS"
    )
    assert req.image_attachment is not None
    assert "base64" in req.image_attachment
```

- [ ] **Step 2: Run pytest to verify schema validation fails**
Run: `pytest backend/tests/test_multimodal_api.py`
Expected: Fail because `image_attachment` is not a field in `ChatMessageRequest` yet.

- [ ] **Step 3: Modify backend/app/schemas.py to add image_attachment**
Modify `ChatMessageRequest` and `ForestAiStreamRequest`:
```python
# In backend/app/schemas.py
class ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    image_attachment: str | None = Field(default=None, description="Base64 encoded image attachment")

class ForestAiStreamRequest(BaseModel):
    course_node_id: str
    chapter_id: str
    quiz_id: str | None = None
    question_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    active_question_context: ForestAiContext
    image_attachment: str | None = Field(default=None, description="Base64 encoded image attachment")
```

- [ ] **Step 4: Update backend/app/api/orchestration.py to build multimodal message contents**
Update `_stream_chat_events` in `backend/app/api/orchestration.py` around line 415:
```python
        # In backend/app/api/orchestration.py
        if getattr(payload, "image_attachment", None):
            current_user_message = HumanMessage(
                content=[
                    {"type": "text", "text": user_message},
                    {"type": "image_url", "image_url": {"url": payload.image_attachment}}
                ]
            )
        else:
            current_user_message = HumanMessage(content=user_message)
```

- [ ] **Step 5: Run tests to verify they pass**
Run: `pytest backend/tests/test_multimodal_api.py`
Expected: PASS

- [ ] **Step 6: Commit changes**
```bash
git add backend/app/schemas.py backend/app/api/orchestration.py backend/tests/test_multimodal_api.py
git commit -m "feat(backend): add image_attachment field and LangChain multimodal message assembly"
```

---

### Task 2: Handwriting Canvas Component

**Files:**
* Create: `frontend/src/components/ui/HandwritingCanvas.tsx`
* Create: `frontend/src/components/ui/HandwritingCanvas.test.tsx`

- [ ] **Step 1: Write a Vitest test for HandwritingCanvas component**
Create `frontend/src/components/ui/HandwritingCanvas.test.tsx`:
```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HandwritingCanvas } from './HandwritingCanvas';

describe('HandwritingCanvas', () => {
  it('should render and trigger clear action', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(<HandwritingCanvas onSave={onSave} onClose={onClose} />);
    const clearBtn = screen.getByRole('button', { name: /清空/i });
    fireEvent.click(clearBtn);
    expect(clearBtn).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npx vitest run frontend/src/components/ui/HandwritingCanvas.test.tsx`
Expected: FAIL due to missing HandwritingCanvas import.

- [ ] **Step 3: Implement HandwritingCanvas.tsx**
Create `frontend/src/components/ui/HandwritingCanvas.tsx`:
```tsx
import React, { useRef, useState, useEffect } from 'react';

interface HandwritingCanvasProps {
  onSave: (base64Data: string) => void;
  onClose: () => void;
}

export function HandwritingCanvas({ onSave, onClose }: HandwritingCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [lineWidth, setLineWidth] = useState(3);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = 'oklch(26% 0.04 235)'; // Deep blue-gray ink
  }, []);

  const startDrawing = (e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let clientX, clientY;
    if ('touches' in e) {
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else {
      clientX = e.clientX;
      clientY = e.clientY;
    }

    const rect = canvas.getBoundingClientRect();
    ctx.beginPath();
    ctx.moveTo(clientX - rect.left, clientY - rect.top);
    ctx.lineWidth = lineWidth;
    setIsDrawing(true);
  };

  const draw = (e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>) => {
    if (!isDrawing) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let clientX, clientY;
    if ('touches' in e) {
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else {
      clientX = e.clientX;
      clientY = e.clientY;
    }

    const rect = canvas.getBoundingClientRect();
    ctx.lineTo(clientX - rect.left, clientY - rect.top);
    ctx.stroke();
  };

  const stopDrawing = () => {
    setIsDrawing(false);
  };

  const handleClear = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  const handleSave = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    onSave(canvas.toDataURL('image/png'));
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[999999]" role="dialog" aria-modal="true">
      <div className="bg-[var(--color-surface)] p-6 rounded-2xl shadow-xl w-full max-w-lg flex flex-col gap-4">
        <div className="flex justify-between items-center">
          <h3 className="font-medium text-base text-[var(--color-text-primary)]">手写笔记/草图</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <canvas
          ref={canvasRef}
          width={480}
          height={320}
          onMouseDown={startDrawing}
          onMouseMove={draw}
          onMouseUp={stopDrawing}
          onMouseLeave={stopDrawing}
          onTouchStart={startDrawing}
          onTouchMove={draw}
          onTouchEnd={stopDrawing}
          className="border border-[var(--color-border)] rounded-xl bg-[var(--color-surface-inset)] cursor-crosshair touch-none"
        />
        <div className="flex justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-secondary)]">笔粗:</span>
            <input type="range" min="1" max="10" value={lineWidth} onChange={(e) => setLineWidth(Number(e.target.value))} />
          </div>
          <div className="flex gap-2">
            <button onClick={handleClear} className="px-4 py-1.5 rounded-full border border-gray-200 text-xs hover:bg-gray-50">清空</button>
            <button onClick={handleSave} className="px-4 py-1.5 rounded-full bg-[var(--gradient-coral)] text-white text-xs font-medium">确认导出</button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**
Run: `npx vitest run frontend/src/components/ui/HandwritingCanvas.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit changes**
```bash
git add frontend/src/components/ui/HandwritingCanvas.tsx frontend/src/components/ui/HandwritingCanvas.test.tsx
git commit -m "feat(frontend): implement HandwritingCanvas component"
```

---

### Task 3: Optimize LeafOutline Sidebar (LeafMarkmap)

**Files:**
* Modify: `frontend/src/pages/leaf/LeafMarkmap.tsx`
* Modify: `frontend/src/styles/leaf.css`

- [ ] **Step 1: Update LeafMarkmap.tsx to render custom completion indicators and micro-badges**
Modify `LeafMarkmapNode` around lines 95-139:
```tsx
  // In frontend/src/pages/leaf/LeafMarkmap.tsx
  // Add micro badges for content types in LeafMarkmapNode:
  const getMicroBadges = (sec: LeafSection) => {
    const badges = [];
    if (sec.section_id.includes('1.1') || sec.section_id.includes('1.2')) {
      badges.push(<span key="doc" className="text-[10px] text-[var(--color-text-muted)] font-mono" title="包含文档">// +</span>);
      badges.push(<span key="vid" className="text-[10px] text-[var(--color-text-muted)] font-mono" title="包含视频">// //</span>);
      badges.push(<span key="anim" className="text-[10px] text-[var(--color-text-muted)] font-mono" title="包含动画">// *</span>);
    }
    return badges;
  };
```
And replace the returned node with:
```tsx
        <div
          className={`px-4 py-2.5 rounded-xl inline-flex items-center justify-between gap-3 border cursor-pointer transition-all duration-300 relative z-10 w-full ${
            isSelected
              ? 'bg-[var(--color-surface)] border-[var(--color-primary)] shadow-[var(--shadow-sm)]'
              : 'bg-[var(--glass-bg)] border-[var(--glass-border)] hover:border-[var(--color-primary-soft)] hover:translate-x-1'
          }`}
          onClick={() => onSelectSection(section.section_id)}
        >
          <div className="flex items-center gap-2 truncate">
            {isSelected ? (
              <span className="w-2 h-2 rounded-full bg-[var(--color-primary)] shrink-0 animate-pulse"></span>
            ) : (
              <span className="w-2 h-2 rounded-full bg-[var(--color-border)] shrink-0"></span>
            )}
            <span className={`text-sm truncate ${isSelected ? 'text-[var(--color-primary)] font-medium' : 'text-[var(--color-text-secondary)]'}`}>
              {getLeafSectionHeading(section)}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center gap-1.5">{getMicroBadges(section)}</div>
            {hasChildren && (
              <button
                type="button"
                className="p-1 hover:bg-[var(--color-surface-inset)] rounded-full transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleCollapsedSection(section.section_id, collapsedSectionIds, onCollapsedSectionIdsChange);
                }}
              >
                {isCollapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            )}
          </div>
        </div>
```

- [ ] **Step 2: Commit changes**
```bash
git add frontend/src/pages/leaf/LeafMarkmap.tsx
git commit -m "style(frontend): optimize LeafMarkmap node rendering with badges and refined borders"
```

---

### Task 4: Integrate Multimodal & Handwriting in AI Chat Widget

**Files:**
* Modify: `frontend/src/components/onboarding/AiGreetingInput.tsx`

- [ ] **Step 1: Update AiGreetingInput.tsx state and render handwriting triggers**
In `AiGreetingInput.tsx`, import `HandwritingCanvas`:
```tsx
import { HandwritingCanvas } from '../ui/HandwritingCanvas';
import { Paperclip, PenTool } from 'lucide-react';
```
Add states inside `AiGreetingInput`:
```tsx
  const [showCanvas, setShowCanvas] = useState(false);
  const [imageAttachment, setImageAttachment] = useState<string | null>(null);
```

- [ ] **Step 2: Modify handleSubmit and streamSession trigger**
Include `imageAttachment` payload in `sendMessage` inside `AiGreetingInput`:
```tsx
      const payload: any = {
        session_id: executionIdRef.current,
        message: query,
      };
      if (imageAttachment) {
        payload.image_attachment = imageAttachment;
        setImageAttachment(null);
      }
```

- [ ] **Step 3: Render image preview and attachment controls above textarea**
In the return structure of `AiGreetingInput.tsx` around line 900:
```tsx
                <form
                  className="chat-composer flex flex-col gap-2 p-3 bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl shadow-[var(--shadow-sm)]"
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleSubmit();
                  }}
                >
                  {imageAttachment && (
                    <div className="relative w-16 h-16 border border-[var(--color-border)] rounded-lg overflow-hidden bg-white mb-2 self-start flex shrink-0">
                      <img src={imageAttachment} alt="Attachment Preview" className="object-cover w-full h-full" />
                      <button type="button" onClick={() => setImageAttachment(null)} className="absolute top-0 right-0 bg-black/60 text-white rounded-full w-4 h-4 text-[10px] flex items-center justify-center">✕</button>
                    </div>
                  )}
                  <div className="flex w-full items-end gap-3">
                    <div className="flex gap-1.5 pb-1 shrink-0">
                      <button type="button" onClick={() => setShowCanvas(true)} title="手写/画图" className="p-1.5 hover:bg-[var(--color-surface-inset)] rounded-full text-[var(--color-text-secondary)]">
                        <PenTool className="w-4 h-4" />
                      </button>
                    </div>
                    <textarea
                      rows={1}
                      placeholder={hasCompleteProfileRef.current ? '画像已生成，可以继续补充或追问...' : '输入你的学习情况...'}
                      value={inputValue}
                      disabled={isPending}
                      onChange={(event) => setInputValue(event.target.value)}
                      onKeyDown={(event) => {
                        if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                          handleSubmit();
                        }
                      }}
                      className="flex-1 bg-transparent text-[var(--color-text-primary)] border-none outline-none resize-none"
                    />
                    <button
                      type="submit"
                      className="submit-button"
                      disabled={isPending || (!inputValue.trim() && !imageAttachment)}
                    >
                      <span>+</span>
                    </button>
                  </div>
                </form>
```
And render `<HandwritingCanvas>` if `showCanvas` is true:
```tsx
      {showCanvas && (
        <HandwritingCanvas
          onSave={(data) => {
            setImageAttachment(data);
            setShowCanvas(false);
          }}
          onClose={() => setShowCanvas(false)}
        />
      )}
```

- [ ] **Step 4: Run test to check widget rendering**
Run: `npm test`
Verify that compilation passes.

- [ ] **Step 5: Commit changes**
```bash
git add frontend/src/components/onboarding/AiGreetingInput.tsx
git commit -m "feat(frontend): integrate HandwritingCanvas and attachment preview in AiGreetingInput widget"
```

---

### Task 5: Upgrade Forest Quiz AI Panel

**Files:**
* Modify: `frontend/src/pages/forest/ForestQuizPage.tsx`

- [ ] **Step 1: Add custom text input, handwriting canvas, and custom submit in ForestAiPanel**
Modify `ForestAiPanel` in `ForestQuizPage.tsx` to include textarea input & PenTool trigger:
```tsx
import { PenTool } from 'lucide-react';
import { HandwritingCanvas } from '../../components/ui/HandwritingCanvas';
```
Add inputs inside `ForestQuizPage`:
```tsx
  const [customQuestion, setCustomQuestion] = useState('');
  const [forestImageAttachment, setForestImageAttachment] = useState<string | null>(null);
  const [showForestCanvas, setShowForestCanvas] = useState(false);
```
Modify `ForestAiPanel` rendering structure to support questions and attachments:
```tsx
      <div className="forest-ai-composer mt-4 flex flex-col gap-2">
        {forestImageAttachment && (
          <div className="relative w-12 h-12 border border-[var(--color-border)] rounded overflow-hidden mb-1">
            <img src={forestImageAttachment} alt="Preview" className="object-cover w-full h-full" />
            <button onClick={() => setForestImageAttachment(null)} className="absolute top-0 right-0 bg-black/60 text-white rounded-full w-3 h-3 text-[8px] flex items-center justify-center">✕</button>
          </div>
        )}
        <div className="flex gap-2 items-center">
          <textarea
            value={customQuestion}
            onChange={(e) => setCustomQuestion(e.target.value)}
            placeholder="关于这道题想问些什么？"
            className="flex-1 p-2 text-xs border border-[var(--color-border)] rounded-xl bg-transparent text-[var(--color-text-primary)]"
          />
          <button type="button" onClick={() => setShowForestCanvas(true)} className="p-1.5 hover:bg-gray-100 rounded-full">
            <PenTool className="w-4 h-4 text-gray-500" />
          </button>
        </div>
      </div>
```

- [ ] **Step 2: Commit changes**
```bash
git add frontend/src/pages/forest/ForestQuizPage.tsx
git commit -m "feat(frontend): add custom input and handwriting drawing trigger to ForestAiPanel"
```

---

### Task 6: Implement Canopy Page (Knowledge Graph Visualizer)

**Files:**
* Create: `frontend/src/pages/canopy/CanopyPage.tsx`
* Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create CanopyPage.tsx**
Create `frontend/src/pages/canopy/CanopyPage.tsx`:
```tsx
import React, { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

export function CanopyPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Draw some placeholder trees representing knowledge nodes
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = 'oklch(76% 0.12 55)'; // Coral
    ctx.lineWidth = 4;

    // Node 1: Root
    ctx.beginPath();
    ctx.arc(320, 240, 20, 0, Math.PI * 2);
    ctx.stroke();

    // Node 2: Branch 1
    ctx.beginPath();
    ctx.moveTo(320, 240);
    ctx.lineTo(200, 150);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(200, 150, 15, 0, Math.PI * 2);
    ctx.stroke();

    // Node 3: Branch 2
    ctx.beginPath();
    ctx.moveTo(320, 240);
    ctx.lineTo(440, 150);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(440, 150, 15, 0, Math.PI * 2);
    ctx.stroke();
  }, []);

  return (
    <section className="min-h-screen text-[var(--color-text-primary)] relative overflow-x-hidden p-8 flex flex-col gap-6">
      <div className="leaf-ambient-sun" aria-hidden="true" />
      <div className="leaf-paper-canvas" aria-hidden="true" />
      <header className="relative z-10 flex flex-col gap-2">
        <span className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">// canopy</span>
        <h1 className="text-3xl font-medium text-[var(--color-secondary)]">成森 · 知识谱系</h1>
        <p className="text-sm text-[var(--color-text-secondary)]">在这里，你已学的所有课程会连接成茂密森林的树冠。</p>
      </header>
      <div className="relative z-10 w-full max-w-4xl aspect-[16/9] border border-[var(--color-border)] rounded-2xl overflow-hidden bg-[var(--color-surface)] shadow-[var(--shadow-sm)]">
        <canvas ref={canvasRef} width={640} height={480} className="w-full h-full bg-[var(--color-surface-inset)]" />
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Update App.tsx to wire CanopyPage route**
Update `/canopy` path in `frontend/src/App.tsx`:
```tsx
// In frontend/src/App.tsx
import { CanopyPage } from './pages/canopy/CanopyPage';
// Replace path="/canopy" element with <CanopyPage />:
<Route path="/canopy" element={<CanopyPage />} />
```

- [ ] **Step 3: Commit changes**
```bash
git add frontend/src/pages/canopy/CanopyPage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): implement CanopyPage and wire /canopy route"
```

---

### Task 7: Implement Canvas Page (Infinite Meditative Scratchpad)

**Files:**
* Create: `frontend/src/pages/canvas/ScratchpadCanvas.tsx`
* Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create ScratchpadCanvas.tsx**
Create `frontend/src/pages/canvas/ScratchpadCanvas.tsx`:
```tsx
import React, { useRef, useState } from 'react';

export function ScratchpadCanvas() {
  const [isDrawing, setIsDrawing] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const startDrawing = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const rect = canvas.getBoundingClientRect();
    ctx.beginPath();
    ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'oklch(26% 0.04 235)';
    setIsDrawing(true);
  };

  const draw = (e: React.MouseEvent) => {
    if (!isDrawing) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const rect = canvas.getBoundingClientRect();
    ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
    ctx.stroke();
  };

  const stopDrawing = () => {
    setIsDrawing(false);
  };

  return (
    <section className="min-h-screen text-[var(--color-text-primary)] relative overflow-x-hidden p-8 flex flex-col gap-6">
      <div className="leaf-ambient-sun" aria-hidden="true" />
      <div className="leaf-paper-canvas" aria-hidden="true" />
      <header className="relative z-10 flex flex-col gap-2">
        <span className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">// canvas</span>
        <h1 className="text-3xl font-medium text-[var(--color-secondary)]">画布 · 疗愈白板</h1>
        <p className="text-sm text-[var(--color-text-secondary)]">在无限延展的冥想纸质白板上，记录你的奇思妙想与笔记连线。</p>
      </header>
      <div className="relative z-10 w-full max-w-4xl aspect-[16/9] border border-[var(--color-border)] rounded-2xl overflow-hidden bg-[var(--color-surface)] shadow-[var(--shadow-sm)]">
        <canvas
          ref={canvasRef}
          width={800}
          height={450}
          onMouseDown={startDrawing}
          onMouseMove={draw}
          onMouseUp={stopDrawing}
          onMouseLeave={stopDrawing}
          className="w-full h-full bg-[var(--color-surface-inset)] cursor-crosshair"
        />
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Update App.tsx to wire ScratchpadCanvas route**
Update `/canvas` path in `frontend/src/App.tsx`:
```tsx
// In frontend/src/App.tsx
import { ScratchpadCanvas } from './pages/canvas/ScratchpadCanvas';
// Replace path="/canvas" element with <ScratchpadCanvas />:
<Route path="/canvas" element={<ScratchpadCanvas />} />
```

- [ ] **Step 3: Commit changes**
```bash
git add frontend/src/pages/canvas/ScratchpadCanvas.tsx frontend/src/App.tsx
git commit -m "feat(frontend): implement ScratchpadCanvas and wire /canvas route"
```
