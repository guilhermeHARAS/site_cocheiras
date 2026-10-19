export function ageLabel(horse, now = new Date()) {
  if (horse.birthDate) {
    const birth = new Date(`${horse.birthDate}T12:00:00`);
    let months = (now.getFullYear() - birth.getFullYear()) * 12 + now.getMonth() - birth.getMonth();
    if (now.getDate() < birth.getDate()) months -= 1;
    months = Math.max(0, months);
    if (months < 12) return `${months} ${months === 1 ? 'mês' : 'meses'}`;
    const years = Math.floor(months / 12);
    return `${years} ${years === 1 ? 'ano' : 'anos'}`;
  }
  if (horse.age !== null && horse.age !== undefined && horse.age !== '') {
    let years = Number(horse.age) || 0;
    if (horse.ageRecordedAt) {
      const reference = new Date(`${horse.ageRecordedAt}T12:00:00`);
      let elapsed = now.getFullYear() - reference.getFullYear();
      if (now.getMonth() < reference.getMonth() || (now.getMonth() === reference.getMonth() && now.getDate() < reference.getDate())) elapsed -= 1;
      years += Math.max(0, elapsed);
    }
    return `${years} ${years === 1 ? 'ano' : 'anos'}`;
  }
  return 'Idade não informada';
}
