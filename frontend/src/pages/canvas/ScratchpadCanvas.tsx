import React, { useRef, useState, useEffect } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import { PenTool, Move, Check, HelpCircle, FileText, Code, Trash } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { streamForestAi } from '../../api/forest';
import { motionTokens } from '../../styles/motion-tokens';

interface CanvasItem {
  id: string;
  type: 'note' | 'course' | 'code';
  x: number;
  y: number;
  content: string;
  title?: string;
  color?: string;
}

interface Point {
  x: number;
  y: number;
}

export function ScratchpadCanvas() {
  const { token } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Viewport transformation states
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<Point>({ x: 0, y: 0 });

  // Tool states: 'pan' | 'brush' | 'lasso'
  const [activeTool, setActiveTool] = useState<'pan' | 'brush' | 'lasso'>('brush');

  // Drawing strokes
  const [strokes, setStrokes] = useState<Point[][]>([]);
  const [currentStroke, setCurrentStroke] = useState<Point[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);

  // Lasso points
  const [lassoPoints, setLassoPoints] = useState<Point[]>([]);
  const [isLassoing, setIsLassoing] = useState(false);

  // Drag-and-drop items
  const [items, setItems] = useState<CanvasItem[]>([
    { id: '1', type: 'note', x: 100, y: 120, content: '多模态 AI 交互脑图：你可以拖拽小卡片，使用画笔在空白区域勾勒逻辑，再用套索框选求助。', color: 'oklch(96% 0.04 95)' },
    { id: '2', type: 'course', x: 400, y: 80, title: '智能体协作开发', content: '使用 supervisor 模式调度各子智能体完成任务。' },
    { id: '3', type: 'code', x: 250, y: 340, content: 'class SupervisorAgent:\n    def __init__(self):\n        self.workers = []' },
  ]);
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null);
  const dragStartOffsetRef = useRef<Point>({ x: 0, y: 0 });

  // Multimodal Lasso Ask Popover
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [askText, setAskText] = useState('');
  const [aiResponse, setAiResponse] = useState('');
  const [aiStatus, setAiStatus] = useState<'idle' | 'streaming' | 'error'>('idle');

  // Handle Zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = 1.1;
    const nextZoom = e.deltaY < 0 ? zoom * zoomFactor : zoom / zoomFactor;
    setZoom(Math.max(0.5, Math.min(nextZoom, 2.5)));
  };

  // Canvas Coordinates Converter
  const getCanvasCoords = (clientX: number, clientY: number): Point => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    return {
      x: (clientX - rect.left - panX) / zoom,
      y: (clientY - rect.top - panY) / zoom,
    };
  };

  // Mouse Interaction Router
  const handleMouseDown = (e: React.MouseEvent) => {
    if (draggingItemId) return;

    if (activeTool === 'pan' || e.button === 1) {
      setIsPanning(true);
      panStartRef.current = { x: e.clientX - panX, y: e.clientY - panY };
      e.preventDefault();
    } else if (activeTool === 'brush') {
      setIsDrawing(true);
      const pt = getCanvasCoords(e.clientX, e.clientY);
      setCurrentStroke([pt]);
    } else if (activeTool === 'lasso') {
      setIsLassoing(true);
      const pt = getCanvasCoords(e.clientX, e.clientY);
      setLassoPoints([pt]);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isPanning) {
      setPanX(e.clientX - panStartRef.current.x);
      setPanY(e.clientY - panStartRef.current.y);
    } else if (isDrawing && currentStroke.length > 0) {
      const pt = getCanvasCoords(e.clientX, e.clientY);
      setCurrentStroke((prev) => [...prev, pt]);
    } else if (isLassoing && lassoPoints.length > 0) {
      const pt = getCanvasCoords(e.clientX, e.clientY);
      setLassoPoints((prev) => [...prev, pt]);
    }
  };

  const handleMouseUp = () => {
    if (isPanning) {
      setIsPanning(false);
    } else if (isDrawing) {
      setIsDrawing(false);
      if (currentStroke.length > 1) {
        setStrokes((prev) => [...prev, currentStroke]);
      }
      setCurrentStroke([]);
    } else if (isLassoing) {
      setIsLassoing(false);
      if (lassoPoints.length > 2) {
        cropLassoedRegion();
      } else {
        setLassoPoints([]);
      }
    }
  };

  // Item dragging
  const handleItemDragStart = (e: React.MouseEvent, item: CanvasItem) => {
    e.stopPropagation();
    setDraggingItemId(item.id);
    dragStartOffsetRef.current = {
      x: e.clientX - item.x * zoom,
      y: e.clientY - item.y * zoom,
    };
  };

  const handleItemDragMove = (e: React.MouseEvent) => {
    if (!draggingItemId) return;
    const item = items.find((it) => it.id === draggingItemId);
    if (!item) return;

    // Calculate new position relative to pan/zoom
    const newX = (e.clientX - dragStartOffsetRef.current.x + item.x * zoom) / zoom;
    const newY = (e.clientY - dragStartOffsetRef.current.y + item.y * zoom) / zoom;

    setItems((prev) =>
      prev.map((it) => (it.id === draggingItemId ? { ...it, x: newX, y: newY } : it))
    );
  };

  const handleItemDragEnd = () => {
    setDraggingItemId(null);
  };

  // Lasso Crop Base64 Generator
  const cropLassoedRegion = () => {
    if (lassoPoints.length < 3) return;
    
    // Bounding Box
    const xs = lassoPoints.map((p) => p.x);
    const ys = lassoPoints.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const width = maxX - minX;
    const height = maxY - minY;

    if (width < 20 || height < 20) {
      setLassoPoints([]);
      return;
    }

    // Create temporary HTML5 canvas to export Base64
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Background paper color oklch
    ctx.fillStyle = '#f9f8f6';
    ctx.fillRect(0, 0, width, height);

    // Draw strokes relative to Crop origin
    ctx.translate(-minX, -minY);
    ctx.strokeStyle = 'oklch(26% 0.04 235)'; // Deep ink blue
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    for (const stroke of strokes) {
      if (stroke.length === 0) continue;
      ctx.beginPath();
      ctx.moveTo(stroke[0].x, stroke[0].y);
      for (let i = 1; i < stroke.length; i++) {
        ctx.lineTo(stroke[i].x, stroke[i].y);
      }
      ctx.stroke();
    }

    // Also draw items falling in this box
    ctx.font = '12px LXGW WenKai, sans-serif';
    ctx.fillStyle = 'oklch(26% 0.04 235)';
    for (const item of items) {
      if (item.x >= minX && item.x <= maxX && item.y >= minY && item.y <= maxY) {
        ctx.strokeRect(item.x, item.y, 150, 80);
        ctx.fillText(item.type === 'course' ? item.title || 'Course' : item.type, item.x + 8, item.y + 20);
        ctx.fillText(item.content.slice(0, 20) + '...', item.x + 8, item.y + 40);
      }
    }

    try {
      setSelectedRegion(canvas.toDataURL('image/png'));
    } catch {
      // Fallback in case of origin security restrictions
      setSelectedRegion('data:image/png;base64,iVBORw0KGgoAAAANS');
    }
    setLassoPoints([]);
  };

  // Add Item Helpers
  const addStickyNote = () => {
    const pt = getCanvasCoords(window.innerWidth / 2, window.innerHeight / 2);
    setItems((prev) => [
      ...prev,
      {
        id: `note-${Date.now()}`,
        type: 'note',
        x: pt.x,
        y: pt.y,
        content: '新便签，双击修改文本...',
        color: 'oklch(95% 0.05 140)',
      },
    ]);
  };

  const addCodeBox = () => {
    const pt = getCanvasCoords(window.innerWidth / 2, window.innerHeight / 2);
    setItems((prev) => [
      ...prev,
      {
        id: `code-${Date.now()}`,
        type: 'code',
        x: pt.x,
        y: pt.y,
        content: '# 编写你的草稿代码...\ndef solve():\n    pass',
      },
    ]);
  };

  // Stream Lasso Prompt to AI
  const handleAskAI = async () => {
    if (!token || !selectedRegion || aiStatus === 'streaming') return;
    setAiStatus('streaming');
    setAiResponse('');

    const mockContext = {
      course_node_id: 'canvas-scratchpad',
      chapter_id: 'global-canvas',
      quiz_id: null,
      question_id: null,
      question: null,
      answer: null,
      grading_result: null,
    };

    try {
      await streamForestAi(
        token,
        mockContext,
        askText || '请解释一下我框选的这些草图与概念之间的关系。',
        (event) => {
          if (event.event === 'forest_ai_text_chunk' && event.chunk) {
            setAiResponse((prev) => prev + event.chunk);
          }
          if (event.event === 'forest_error') {
            setAiStatus('error');
            setAiResponse(event.message ?? 'AI 暂时不可用');
          }
          if (event.event === 'forest_ai_completed') {
            setAiStatus('idle');
          }
        },
        selectedRegion
      );
    } catch (err) {
      setAiStatus('error');
      setAiResponse(err instanceof Error ? err.message : 'AI 暂时不可用');
    }
  };

  return (
    <CanvasWrapper
      ref={containerRef}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={(e) => {
        handleMouseMove(e);
        handleItemDragMove(e);
      }}
      onMouseUp={() => {
        handleMouseUp();
        handleItemDragEnd();
      }}
      aria-label="画布白板空间"
    >
      {/* Meditative Sun Background */}
      <div className="forest-ambient-sun" aria-hidden="true" />

      {/* Infinite Canvas Container */}
      <div
        className="canvas-viewport"
        style={{
          transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
          transformOrigin: '0 0',
        }}
      >
        {/* Draw strokes */}
        <svg className="drawing-overlay" style={{ pointerEvents: 'none' }}>
          {strokes.map((stroke, index) => (
            <path
              key={index}
              d={`M ${stroke.map((p) => `${p.x} ${p.y}`).join(' L ')}`}
              fill="none"
              stroke="oklch(26% 0.04 235)"
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {currentStroke.length > 0 && (
            <path
              d={`M ${currentStroke.map((p) => `${p.x} ${p.y}`).join(' L ')}`}
              fill="none"
              stroke="oklch(26% 0.04 235)"
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
          
          {/* Drawing Lasso */}
          {lassoPoints.length > 0 && (
            <polygon
              points={lassoPoints.map((p) => `${p.x},${p.y}`).join(' ')}
              fill="oklch(76% 0.11 75 / 0.08)"
              stroke="oklch(76% 0.11 75)"
              strokeWidth={1.5}
              strokeDasharray="4,4"
            />
          )}
        </svg>

        {/* Drag-and-drop Items */}
        {items.map((item) => (
          <div
            key={item.id}
            className={`canvas-item-wrapper ${item.type}`}
            style={{
              left: `${item.x}px`,
              top: `${item.y}px`,
              backgroundColor: item.color,
            }}
            onMouseDown={(e) => handleItemDragStart(e, item)}
          >
            <div className="item-drag-handle">
              <Move className="w-3.5 h-3.5 text-gray-400" />
              <button
                className="item-delete-btn"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setItems((prev) => prev.filter((it) => it.id !== item.id))}
              >
                <Trash className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="item-content-body">
              {item.type === 'course' && <h4>{item.title}</h4>}
              {item.type === 'code' ? (
                <textarea
                  value={item.content}
                  onMouseDown={(e) => e.stopPropagation()}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((it) => (it.id === item.id ? { ...it, content: e.target.value } : it))
                    )
                  }
                  className="code-textarea"
                />
              ) : (
                <textarea
                  value={item.content}
                  onMouseDown={(e) => e.stopPropagation()}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((it) => (it.id === item.id ? { ...it, content: e.target.value } : it))
                    )
                  }
                  className="note-textarea"
                />
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Floating Toolbar */}
      <div className="canvas-toolbar">
        <button
          className={activeTool === 'brush' ? 'is-active' : ''}
          onClick={() => setActiveTool('brush')}
          title="画笔"
        >
          <PenTool className="w-5 h-5" />
        </button>
        <button
          className={activeTool === 'lasso' ? 'is-active' : ''}
          onClick={() => setActiveTool('lasso')}
          title="套索工具 (框选追问)"
        >
          <HelpCircle className="w-5 h-5" />
        </button>
        <button
          className={activeTool === 'pan' ? 'is-active' : ''}
          onClick={() => setActiveTool('pan')}
          title="移动画布"
        >
          <Move className="w-5 h-5" />
        </button>
        <div className="divider" />
        <button onClick={addStickyNote} title="新建便签">
          <FileText className="w-5 h-5" />
        </button>
        <button onClick={addCodeBox} title="代码容器">
          <Code className="w-5 h-5" />
        </button>
      </div>

      {/* Lasso Ask Modal Dialog */}
      <AnimatePresence>
        {selectedRegion && (
          <motion.div
            className="lasso-ask-modal"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={motionTokens.lazy}
          >
            <div className="modal-header">
              <h3>对框选区域发起追问</h3>
              <button onClick={() => setSelectedRegion(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="crop-preview-box">
                <img src={selectedRegion} alt="Lasso Crop" className="crop-img" />
              </div>
              <textarea
                placeholder="在此输入你针对框选演算草图/概念的疑惑..."
                value={askText}
                onChange={(e) => setAskText(e.target.value)}
              />
              <button
                type="button"
                className="modal-send-btn"
                onClick={handleAskAI}
                disabled={aiStatus === 'streaming'}
              >
                {aiStatus === 'streaming' ? '分析中...' : '提交求助'}
              </button>
              {aiResponse && (
                <div className="ai-response-box">
                  <strong>Forest AI 解析:</strong>
                  <p>{aiResponse}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </CanvasWrapper>
  );
}

const CanvasWrapper = styled.section`
  position: relative;
  width: 100%;
  height: 100svh;
  overflow: hidden;
  background: 
    radial-gradient(circle, oklch(90% 0.01 240 / 0.16) 1px, transparent 1px),
    var(--gradient-paper);
  background-size: 24px 24px;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }

  .forest-ambient-sun {
    position: absolute;
    top: -100px;
    right: -100px;
    width: 450px;
    height: 450px;
    border-radius: var(--radius-full);
    background: var(--effect-sun-glow);
    filter: var(--effect-blur-sun);
    opacity: 0.5;
    pointer-events: none;
  }

  .canvas-viewport {
    position: absolute;
    width: 100%;
    height: 100%;
  }

  .drawing-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 5000px;
    height: 5000px;
  }

  /* Drag & Drop Cards styling */
  .canvas-item-wrapper {
    position: absolute;
    width: 220px;
    padding: var(--space-12);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    background: var(--color-surface);
    cursor: default;
  }

  .canvas-item-wrapper.note {
    background: oklch(96% 0.04 95);
  }

  .canvas-item-wrapper.course {
    background: oklch(94% 0.02 240);
    border-left: 4px solid var(--color-primary);
  }

  .canvas-item-wrapper.code {
    background: oklch(18% 0.02 240);
    color: oklch(90% 0.02 240);
    border: 1px solid oklch(90% 0.02 240 / 0.12);
    width: 280px;
  }

  .item-drag-handle {
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: move;
    border-bottom: 1px solid var(--color-border);
    padding-bottom: var(--space-4);
  }

  .canvas-item-wrapper.code .item-drag-handle {
    border-bottom: 1px solid oklch(90% 0.02 240 / 0.12);
  }

  .item-delete-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--color-text-secondary);
  }

  .item-delete-btn:hover {
    color: var(--color-error);
  }

  .item-content-body h4 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-body-sm);
    color: var(--color-secondary);
  }

  .note-textarea,
  .code-textarea {
    width: 100%;
    min-height: 80px;
    border: none;
    outline: none;
    resize: none;
    background: transparent;
    font-family: var(--font-body);
    font-size: var(--text-caption);
    line-height: 1.5;
  }

  .code-textarea {
    font-family: var(--font-code);
    color: oklch(90% 0.02 240);
  }

  /* Toolbar */
  .canvas-toolbar {
    position: absolute;
    bottom: var(--space-32);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--space-8);
    background: var(--glass-bg);
    backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-16);
    box-shadow: var(--shadow-md);
    z-index: 100;
  }

  .canvas-toolbar button {
    width: 40px;
    height: 40px;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all var(--duration-lazy-hover) var(--ease-lazy);
  }

  .canvas-toolbar button:hover {
    background: var(--color-surface-inset);
    color: var(--color-text-primary);
  }

  .canvas-toolbar button.is-active {
    background: var(--gradient-coral);
    color: var(--color-text-inverse);
    box-shadow: var(--shadow-sm);
  }

  .canvas-toolbar .divider {
    width: 1px;
    height: 20px;
    background: var(--color-border);
    margin: 0 var(--space-4);
  }

  /* Lasso Popover */
  .lasso-ask-modal {
    position: absolute;
    top: var(--space-32);
    right: var(--space-32);
    width: 360px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    display: flex;
    flex-direction: column;
    gap: var(--space-12);
    padding: var(--space-24);
    z-index: 1000;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .modal-header h3 {
    margin: 0;
    font-size: var(--text-h4);
    color: var(--color-secondary);
  }

  .modal-header button {
    background: none;
    border: none;
    font-size: var(--text-body);
    cursor: pointer;
    color: var(--color-text-secondary);
  }

  .modal-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-12);
  }

  .crop-preview-box {
    width: 100%;
    aspect-ratio: 16/10;
    border-radius: var(--radius-md);
    background: var(--color-surface-inset);
    border: 1px solid var(--color-border);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .crop-img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .modal-body textarea {
    width: 100%;
    min-height: 80px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-12);
    outline: none;
    resize: vertical;
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
  }

  .modal-send-btn {
    width: 100%;
    padding: var(--space-12);
    border: none;
    border-radius: var(--radius-full);
    background: var(--gradient-coral);
    color: var(--color-text-inverse);
    font-weight: var(--font-weight-medium);
    cursor: pointer;
    box-shadow: var(--shadow-sm);
  }

  .modal-send-btn:disabled {
    cursor: not-allowed;
    opacity: 0.64;
  }

  .ai-response-box {
    margin-top: var(--space-8);
    padding: var(--space-12);
    background: var(--color-surface-inset);
    border-radius: var(--radius-md);
    border-left: 3px solid var(--color-primary);
  }

  .ai-response-box strong {
    font-size: var(--text-caption);
    color: var(--color-primary);
  }

  .ai-response-box p {
    margin: var(--space-4) 0 0;
    font-size: var(--text-body-sm);
    line-height: 1.5;
  }
`;
