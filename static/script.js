data.forEach(item=>{
    html += `
    <li class="list-group-item bg-dark text-white border-secondary">
        ${item.question || item}
    </li>`;
});