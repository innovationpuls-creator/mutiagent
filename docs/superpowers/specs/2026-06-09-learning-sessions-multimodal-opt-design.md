# Spec: Learning Sessions Optimization and Multimodal Enhancements Design

## 1. Introduction & Background
This document specifies the technical design for optimizing existing learning sessions (Branch, Leaf, Forest) and implementing new sessions (Canopy, Canvas) in the "One-Tree" multi-agent learning planning system. The Sprout onboarding session will remain intact.

The design respects the **Headspace meditation style** (warm tones, soft shadows, double-border cards, paper texture, organic animations) as described in `docs/session-desgin.md` and related design system documentation.

---

## 2. Requirements & Scope

### 2.1 Session 2: 繁枝 (Branch Page)
* **Objective**: Enhance the yearly learning path visualization to feel more organic and visually premium.
* **Key Features**:
  * Organic connected path nodes (tree branch style, using custom SVG bezier curves instead of straight lines).
  * Hover glow using HSL/OKLCH color tokens (`--color-primary-soft`, `--effect-peach-glow`).
  * Smooth year-to-year transitional animations using Framer Motion.

### 2.2 Session 3: 叶茂 (Leaf Page - Left Outline)
* **Objective**: Refine the left-hand navigation sidebar (`LeafMarkmap`) to feel more delicate and informative.
* **Key Features**:
  * Reconstruct node navigation pills into structured, double-bordered card elements.
  * Add **progress indicators**: Small status dots indicating if a section is completed (sage green check/dot), in-progress (orange halo), or locked (muted lock).
  * Add **content-type micro-badges**: Sub-icons indicating the presence of a video (`//`), document (`+`), or interactive animation (`*`).
  * Smooth translation-based hover effects (micro-movements to the right with background warm wash).

### 2.3 Session 4: 成林 (Forest Page - AI Panel)
* **Objective**: Enable custom text input and multimodal (handwriting/drawing & image upload) interactions within the Forest AI panel.
* **Key Features**:
  * Add a textarea in `ForestAiPanel` for custom query input.
  * Embed a handwriting canvas (`HandwritingCanvas`) drawer that lets students draw diagrams, equations, or code flows with mouse/stylus.
  * Embed a file upload mechanism to let students upload screenshots or photos of handwritten notes.
  * Add inline thumbnail previews of the sketch/uploaded image with a remove action.
  * Render sent image/drawing attachments inline in the chat message flow.

### 2.4 Session 5: 成森 (Canopy Page - NEW)
* **Objective**: Implement the Canopy page (`/canopy`) to visualize the student's macro-level knowledge forest.
* **Key Features**:
  * An interactive knowledge network graph (using D3.js or HTML5 Canvas/SVG) displaying all course nodes, grade levels, and their interconnections.
  * Learning stats dashboard:
    - "Growth Rings" showing study milestones.
    - Completed course counts, quiz passing rates, and active study time.
  - Meditative warm-lit background with subtle sun glow.

### 2.5 Session 6: 画布 (Canvas Page - NEW)
* **Objective**: Implement the Canvas page (`/canvas`) as an infinite meditative scratchpad workspace.
* **Key Features**:
  * Infinite scrollable, zoomable canvas paper.
  * Add sticky notes, drag-and-drop course section cards, code boxes, and handwriting drawing brush.
  * **Lasso Selection Tool**: Let students lasso-select a region of drawing/text on the canvas, snapshot it, and directly send it to the AI panel for explanation.

---

## 3. Architecture & Technical Design

### 3.1 Handwriting Drawing Engine (`HandwritingCanvas.tsx`)
A new React component that handles custom sketches and drawings.
* **Implementation**: HTML5 `<canvas>` element with pointer events (supporting touch, stylus, and mouse).
* **States**:
  - Drawing state: `isDrawing`, `history` (for undo/redo), `brushColor`, `brushWidth`.
  - Export: Captured as a base64 png data url on commit.
* **Styling**: Warm paper texture background (`--color-surface-inset`), round brush tip.

### 3.2 Outline Tree Refactoring (`LeafMarkmap.tsx`)
Optimize the outline structure.
* **Connection lines**: Replaced with SVG curved branch lines to represent the tree growth metaphor.
* **Node Cards**: Wrapped in Framer Motion `<motion.div>` for smooth hover translation (`x: 4px`, `--duration-lazy-hover`).

### 3.3 Canopy Graph Visualization (`CanopyPage.tsx`)
A new page mapping knowledge nodes.
* **Implementation**: D3-force layout mapping `UserCourseKnowledgeOutline` items.
* **Interactions**: Dragging, zooming, clicking nodes to view course completion summaries or navigations.

### 3.4 Backend API & Multimodal Payload Integration
* **Schemas**:
  `ChatMessageRequest` and `ForestAiStreamRequest` will include an optional base64 image data field:
  ```python
  class ChatMessageRequest(BaseModel):
      session_id: str
      message: str
      image_attachment: str | None = None  # base64 data URL
  ```
* **LangChain Integration**:
  The backend parses `image_attachment`. If present, it creates a multimodal content list for the LangChain `HumanMessage`:
  ```python
  message_content = [
      {"type": "text", "text": user_message},
      {"type": "image_url", "image_url": {"url": image_attachment}}
  ]
  message = HumanMessage(content=message_content)
  ```

---

## 4. Verification & Testing Plan

### 4.1 Automated Testing
* **Canvas Component Tests**: Mock mouse/pointer events to verify coordinates tracking, canvas state history (undo/redo), and image export.
* **Multimodal Serialization Tests**: Verify that base64 images are correctly formatted in frontend requests and decoded/passed to LangChain messages on the backend.
* **Regression Tests**: Ensure existing Sprout onboarding page functionality remains intact.

### 4.2 Visual Verification
* Ensure fonts are rendered correctly via LXGW WenKai.
* Verify OKLCH colors, spacing scales (`--space-*`), and multishadow tokens (`--shadow-sm/md/lg`).
* Test prefers-reduced-motion CSS support.
