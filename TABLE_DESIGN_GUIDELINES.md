# Premium Table Design Guidelines

This project uses a premium table design pattern. When generating or refactoring tables, always adhere to the following rules:

1. **Table Classes**: Use `<table class="table table-hover align-middle">`.
2. **Padding and Transitions**: `theme.css` provides enhanced padding (`1.25rem 1rem`) and a subtle background color transition on row hover out-of-the-box for `.table-hover`.
3. **Typography Hierarchy**:
   - Primary data (like Usernames or primary IDs) should use `<span class="table-primary-text">`.
   - Secondary data (like Email, Designation, Dates) should use `<span class="table-secondary-text">`. This mutes the text and makes it slightly smaller.
4. **Soft Badges**: NEVER use solid bright badges (e.g. `bg-primary`, `bg-success`). Instead, use the custom soft badges defined in `theme.css`:
   - `badge-soft-primary`
   - `badge-soft-success`
   - `badge-soft-info`
   - `badge-soft-warning`
   - `badge-soft-secondary`
   Always include `rounded-pill fw-normal px-2 py-1` with these badge classes to make them look like elegant pills.
5. **Ghost Action Buttons**: Do not use standard outline buttons for row actions. Use the custom ghost button classes:
   - `btn-ghost-primary`
   - `btn-ghost-warning`
   - `btn-ghost-danger`
   These appear as faint icons that highlight beautifully on hover, reducing visual clutter.

### Example Row:

```html
<tr style="cursor: pointer;">
  <td>
    <span class="table-primary-text">John Doe</span>
    <span class="table-secondary-text">john.doe@example.com</span>
  </td>
  <td>
    <span class="badge badge-soft-success rounded-pill fw-normal px-2 py-1">Active</span>
  </td>
  <td class="text-nowrap">
    <button class="btn btn-ghost-primary btn-sm me-1"><i class="bi bi-pencil"></i></button>
    <button class="btn btn-ghost-danger btn-sm"><i class="bi bi-trash"></i></button>
  </td>
</tr>
```
