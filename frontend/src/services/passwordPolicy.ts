export function validNewPassword(password: string): boolean {
  return Array.from(password).length >= 8 && Array.from(password).length <= 128 && /[!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~]/.test(password);
}
