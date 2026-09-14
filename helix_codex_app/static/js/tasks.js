/* Task board drag-and-drop and the card status control.
 *
 * Each card is draggable; dropping on a column posts the new status via
 * HTMX and swaps the board, so the source of truth is the server. The card
 * also carries a status select for touch devices, where drag is unreliable.
 */
function tasksBoard() {
  return {
    draggedTaskId: null,
    dragStart: function (event, taskId) {
      this.draggedTaskId = taskId;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", taskId);
    },
    dragEnd: function () {
      this.draggedTaskId = null;
    },
    dragOver: function (event) {
      event.dataTransfer.dropEffect = "move";
    },
    drop: function (event, status) {
      event.preventDefault();
      var taskId = this.draggedTaskId || event.dataTransfer.getData("text/plain");
      this.draggedTaskId = null;
      if (!taskId) return;
      htmx.ajax("POST", "/app/api/tasks/" + taskId + "/status", {
        values: { status: status },
        target: "#task-board",
        swap: "outerHTML",
        headers: { "X-CSRF-Token": csrfToken() },
      });
    },
    move: function (event, taskId) {
      var status = event.target.value;
      htmx.ajax("POST", "/app/api/tasks/" + taskId + "/status", {
        values: { status: status },
        target: "#task-board",
        swap: "outerHTML",
        headers: { "X-CSRF-Token": csrfToken() },
      });
    },
  };
}

function csrfToken() {
  var meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute("content") : "";
}
